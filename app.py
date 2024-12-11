from flask import Flask, request, render_template, redirect, url_for
import mysql.connector
from datetime import datetime, timedelta
import calendar
from decimal import Decimal


app = Flask(__name__)

# MySQL Connection Setup
db_config = {
    'host': 'localhost',
    'user': 'root',  
    'password': '',  
    'database': 'employee_system'
}


# Function to create monthly tables
def create_monthly_table():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Get current month and year
        today = datetime.now()
        month = today.month
        year = today.year

        # Create table for the current month if it doesn't exist
        table_name = f"attendance_{year}_{month:02d}"

        # Check if table exists
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        result = cursor.fetchone()

        if not result:
            # Create the new table
            cursor.execute(f'''
                CREATE TABLE {table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    employee_id INT NOT NULL,
                    arrival_time TIME,
                    leave_time TIME,
                    is_absent BOOLEAN,
                    worked_hours DECIMAL(5, 2),
                    date DATE
                )
            ''')
            conn.commit()

        conn.close()
    except mysql.connector.Error as err:
        print(f"Error creating table: {err}")

def insert_attendance(employee_id, arrival_time, leave_time, is_absent, worked_hours):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Get current month and year for table name
        today = datetime.now()
        month = today.month
        year = today.year
        table_name = f"attendance_{year}_{month:02d}"

        # Insert the attendance record into the corresponding table
        cursor.execute(f'''
            INSERT INTO {table_name} (employee_id, arrival_time, leave_time, is_absent, worked_hours)
            VALUES (%s, %s, %s, %s, %s)
        ''', (employee_id, arrival_time, leave_time, is_absent, worked_hours))
        conn.commit()
        conn.close()
    except mysql.connector.Error as err:
        print(f"Error inserting attendance: {err}")

# Function to clean up old attendance tables (older than 12 months)
def cleanup_old_tables():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Get current month and year
        today = datetime.now()
        current_month = today.month
        current_year = today.year
        
        # Remove attendance tables older than 12 months
        for i in range(1, 13):  # Check last 12 months
            month_to_check = current_month - i
            year_to_check = current_year
            if month_to_check <= 0:
                month_to_check += 12
                year_to_check -= 1
            
            # Create the table name for that month
            table_name = f"attendance_{year_to_check}_{month_to_check:02d}"
            
            # Drop the table if it exists
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            result = cursor.fetchone()
            if result:
                cursor.execute(f"DROP TABLE {table_name}")
                conn.commit()
        
        conn.close()
    except mysql.connector.Error as err:
        print(f"Error cleaning up old tables: {err}")

# Initialize the setup on app startup
def initialize():
    create_monthly_table()  # Create current month table if it doesn't exist
    cleanup_old_tables()  # Clean up old tables


# Home route (attendance form)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    employee_id = request.form['employee_id']
    is_absent = 'is_absent' in request.form

    # Parse arrival, leave, and break times from inputs
    try:
        arrival_hour = int(request.form.get('arrival_hour', 0))
        arrival_minute = int(request.form.get('arrival_minute', 0))
        leave_hour = int(request.form.get('leave_hour', 0))
        leave_minute = int(request.form.get('leave_minute', 0))
        break_minutes = int(request.form.get('break_minutes', 0))

        if not (0 <= arrival_hour <= 23 and 0 <= arrival_minute <= 59):
            raise ValueError("Invalid arrival time")
        if not (0 <= leave_hour <= 23 and 0 <= leave_minute <= 59):
            raise ValueError("Invalid leave time")
        if not (0 <= break_minutes <= 720):
            raise ValueError("Invalid break time")
    except ValueError as e:
        print(f"Input Error: {e}")
        return "Invalid time input", 400

    arrival_time = None
    leave_time = None
    worked_hours = Decimal(0)

    if not is_absent:
        try:
            arrival_time = datetime.strptime(f"{arrival_hour:02}:{arrival_minute:02}", "%H:%M")
            leave_time = datetime.strptime(f"{leave_hour:02}:{leave_minute:02}", "%H:%M")

            allowable_break_minutes = 45
            extra_break_minutes = max(break_minutes - allowable_break_minutes, 0)

            worked_seconds = (leave_time - arrival_time).seconds - (extra_break_minutes * 60)
            worked_hours = Decimal(max(worked_seconds, 0)) / Decimal(3600)
        except Exception as e:
            print(f"Error parsing times: {e}")
            return "Invalid time input", 400

    insert_attendance(employee_id, arrival_time, leave_time, is_absent, worked_hours)

    return redirect(url_for('index'))



# Route to calculate monthly salary
@app.route('/calculate_salary')
def calculate_salary():
    try:
        # Get the current month and year
        today = datetime.now()
        month = today.month
        year = today.year

        # Create the table name for the current month
        table_name = f"attendance_{year}_{month:02d}"

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Fetch attendance data and join with employees table
        cursor.execute(f'''
            SELECT a.employee_id, e.basic_salary, SUM(a.worked_hours) AS total_hours, 
                COUNT(IF(a.is_absent = 1, 1, NULL)) AS total_absences
            FROM {table_name} a
            JOIN employees e ON a.employee_id = e.employee_id
            GROUP BY a.employee_id, e.basic_salary
        ''')
        attendance_data = cursor.fetchall()

        salaries = []

        for record in attendance_data:
            employee_id = record['employee_id']
            basic_salary = Decimal(record['basic_salary'])
            total_hours = Decimal(record['total_hours'] or 0)
            total_absences = Decimal(record['total_absences'] or 0)

            # Counted absences: Deduct absences beyond the allowed limit (2 absences)
            allowed_absences = 2
            counted_absences = max(Decimal(0), total_absences - allowed_absences)

            # Add the allowed absences to the worked hours (assuming 9 hours per day for allowed absences)
            total_hours_with_allowed_absences = total_hours + (allowed_absences * Decimal(9))  # 9 hours per day for the absences

            # Daily wage calculation (based on basic salary and 30 days per month)
            daily_wage = basic_salary / Decimal(30)

            # Expected hours per month (9 hours/day for 30 days)
            expected_hours_per_month = Decimal(9) * Decimal(30)

            # Adjust total_expected_hours to account for the excess absences (no salary deduction for allowed absences)
            total_expected_hours = Decimal(9) * (Decimal(30) - counted_absences)  # Adjust for excess absences only

            # Calculate salary proportionate to worked hours (based on total worked hours / expected hours)
            salary_from_hours = (total_hours_with_allowed_absences / expected_hours_per_month) * basic_salary

            # Deduction for excess absences beyond the allowed limit (based on daily wage)
            deductions_for_absences = daily_wage * counted_absences

            # Overtime calculation (extra hours worked beyond the expected hours)
            overtime = max(Decimal(0), total_hours_with_allowed_absences - total_expected_hours)
            overtime_pay = (daily_wage / Decimal(9)) * overtime  # Pay for overtime is proportional to daily wage

            # Bonus for no absences (only if total_absences is 0)
            bonus_for_no_absence = daily_wage if total_absences == 0 else Decimal(0)

            # Final salary calculation
            salary = (
                salary_from_hours
                + overtime_pay
                + bonus_for_no_absence
            )

            # Ensure salary is never negative
            salary = max(Decimal(0), salary)

            # Add detailed data to the salaries list
            salaries.append({
                'employee_id': employee_id,
                'basic_salary': round(basic_salary, 2),
                'total_hours': round(total_hours, 2),
                'total_absences': total_absences,  # Ensure absences are included in the data sent to the template
                'counted_absences': counted_absences,
                'salary': round(salary, 2)
            })

        conn.close()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error calculating salaries"

    return render_template('salaries.html', salaries=salaries)


# Route to show employee attendance history by day for a specific month
@app.route('/attendance_record/<int:employee_id>/<int:year>/<int:month>', endpoint='employee_attendance')
def attendance_record(employee_id, year, month):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute('''
            SELECT 
                DAY(a.arrival_time) AS day, 
                a.arrival_time, 
                a.leave_time, 
                a.is_absent, 
                a.worked_hours
            FROM attendance a
            WHERE a.employee_id = %s AND YEAR(a.arrival_time) = %s AND MONTH(a.arrival_time) = %s
            ORDER BY a.arrival_time
        ''', (employee_id, year, month))

        attendance_data = cursor.fetchall()

        days_in_month = list(range(1, calendar.monthrange(year, month)[1] + 1))
        attendance_by_day = []

        for day in days_in_month:
            record = next((r for r in attendance_data if r['day'] == day), None)
            if record:
                # Handle arrival_time and leave_time for existing records
                if record['arrival_time'] is not None:
                    if isinstance(record['arrival_time'], datetime):
                        arrival_time_str = record['arrival_time'].strftime("%H:%M")
                    elif isinstance(record['arrival_time'], timedelta):
                        total_seconds = int(record['arrival_time'].total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        arrival_time_str = f"{hours:02d}:{minutes:02d}"
                    else:
                        arrival_time_str = 'N/A'    
                else:
                    arrival_time_str = 'N/A'

                if record['leave_time'] is not None:
                    if isinstance(record['leave_time'], datetime):
                        leave_time_str = record['leave_time'].strftime("%H:%M")
                    elif isinstance(record['leave_time'], timedelta):
                        total_seconds = int(record['leave_time'].total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        leave_time_str = f"{hours:02d}:{minutes:02d}"
                    else:
                        leave_time_str = 'N/A'
                else:
                    leave_time_str = 'N/A'

                attendance_by_day.append({
                    'day': day,
                    'arrival_time': arrival_time_str,
                    'leave_time': leave_time_str,
                    'is_absent': 'Yes' if record['is_absent'] else 'No',
                    'worked_hours': round(record['worked_hours'], 2) if record['worked_hours'] else 0
                })
            else:
                attendance_by_day.append({
                    'day': day,
                    'arrival_time': 'N/A',
                    'leave_time': 'N/A',
                    'is_absent': 'Yes',
                    'worked_hours': 0
                })

        conn.close()

        return render_template('attendance_record.html', attendance=attendance_by_day, year=year, month=month, employee_id=employee_id)

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        return "Error fetching attendance records."


@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if request.method == 'POST':
        name = request.form['name']
        position = request.form['position']
        basic_salary = request.form['basic_salary']
        

        try:
            # Connect to the MySQL database
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()

            # Insert the new employee into the 'employees' table
            cursor.execute('''
                INSERT INTO employees (name, position, basic_salary)
                VALUES (%s, %s, %s)
            ''', (name, position, basic_salary))

            conn.commit()
            conn.close()

            return redirect(url_for('index'))

        except mysql.connector.Error as err:
            print(f"Error inserting employee: {err}")
            return "Error adding employee", 500

    return render_template('add_employee.html')



@app.route('/employees', methods=['GET'])
def list_employees():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Fetch all employees from the database
        cursor.execute('SELECT * FROM employees')
        employees = cursor.fetchall()

        conn.close()

        # Render the employee list template
        return render_template('employee_list.html', employees=employees)
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error fetching employees", 500



@app.route('/delete_employee/<int:employee_id>', methods=['POST'])
def delete_employee(employee_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Delete the employee from the database
        cursor.execute('DELETE FROM employees WHERE employee_id = %s', (employee_id,))
        conn.commit()

        conn.close()

        # Redirect back to the employee list after deletion
        return redirect(url_for('list_employees'))
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return "Error deleting employee", 500

@app.route('/edit_employee/<int:employee_id>', methods=['GET', 'POST'])
def edit_employee(employee_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        name = request.form['name']
        position = request.form['position']
        basic_salary = request.form['basic_salary']
        
        
        cursor.execute("""
            UPDATE employees
            SET name = %s, position = %s, basic_salary = %s
            WHERE employee_id = %s
        """, (name, position, basic_salary, employee_id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('list_employees'))
    
    cursor.execute("SELECT * FROM employees WHERE employee_id = %s", (employee_id,))
    employee = cursor.fetchone()
    conn.close()
    return render_template('edit_employee.html', employee=employee)


# Run the app
if __name__ == '__main__':
    # Initialize tables and cleanup old tables before the app starts handling requests
    initialize()
    app.run(debug=True)
