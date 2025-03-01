from flask import Flask, request, render_template, redirect, url_for , jsonify , flash
import mysql.connector
from datetime import datetime, timedelta , date , time
import calendar
from decimal import Decimal
import os
import traceback  
import logging
from mysql.connector import pooling
from flask import abort


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


app = Flask(__name__)

app.debug = False  # Explicitly set debug mode to False in production
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise ValueError("FLASK_SECRET_KEY environment variable not set.")


# MySQL Connection Setup
db_config = {
    'host': 'localhost',
    'user': 'flaskuser',  
    'password': 'M1y2s3q4l5!6',  
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

        table_name = f"attendance_{year}_{month:02d}"

        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        result = cursor.fetchone()

        if not result:
            cursor.execute(f'''
                  CREATE TABLE {table_name} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                employee_id INT NOT NULL,
                arrival_time TIME,
                leave_time TIME,
                is_absent BOOLEAN,
                worked_hours DECIMAL(5, 2),
                date DATE,  -- Add the date column here
                is_holiday BOOLEAN
                )
            ''')
            conn.commit()

        conn.close()
    except mysql.connector.Error as err:
        print(f"Error creating table: {err}")


from datetime import time

def insert_attendance(employee_id, arrival_time, leave_time, is_absent, worked_hours, is_holiday, today):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        table_name = f"attendance_{today.year}_{today.month:02d}"
        print(f"Table: {table_name}")

        query = f"""
            INSERT INTO {table_name} (employee_id, arrival_time, leave_time, is_absent, worked_hours, date, is_holiday)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        values = (employee_id, arrival_time, leave_time, is_absent, float(worked_hours), today, is_holiday)

        print(f"Inserting values: {values}")
        cursor.execute(query, values)
        conn.commit()
        print("Attendance inserted successfully.")

    except mysql.connector.Error as err:
        print(f"MySQL Error inserting attendance: {err}")
        conn.rollback() 
    except Exception as e:
        print(f"General Error inserting attendance: {e}")
        conn.rollback() 
        traceback.print_exc()
    finally:
        if conn.is_connected():
            conn.close()

# Function to clean up old attendance tables (older than 12 months)
def cleanup_old_tables():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
       
        today = datetime.now()
        current_month = today.month
        current_year = today.year
        
        
        for i in range(1, 13):  # Check last 12 months
            month_to_check = current_month - i
            year_to_check = current_year
            if month_to_check <= 0:
                month_to_check += 12
                year_to_check -= 1
            
            
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


from datetime import datetime
from decimal import Decimal


@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    print("Request Form:", request.form)

    employee_id = request.form.get('employee_id')
    print("Employee ID:", employee_id)

    is_absent = 'is_absent' in request.form
    print("Is Absent:", is_absent)

    is_holiday = 1 if request.form.get('is_holiday', 'off') == 'on' else 0
    print("Is Holiday:", is_holiday)

    arrival_time = None
    leave_time = None
    worked_hours = Decimal(0)

    if is_holiday:
        worked_hours = Decimal(9)
        print("Marked as Holiday, Worked Hours set to 9")
    elif is_absent:
        worked_hours = Decimal(0)
        print("Marked as Absent, Worked Hours set to 0")
    else:
        arrival_hour = request.form.get('arrival_hour')
        arrival_minute = request.form.get('arrival_minute')
        leave_hour = request.form.get('leave_hour')
        leave_minute = request.form.get('leave_minute')

        print("Arrival Hour:", arrival_hour)
        print("Arrival Minute:", arrival_minute)
        print("Leave Hour:", leave_hour)
        print("Leave Minute:", leave_minute)

        if all([arrival_hour, arrival_minute, leave_hour, leave_minute]):
            try:
                arrival_hour = int(arrival_hour)
                arrival_minute = int(arrival_minute)
                leave_hour = int(leave_hour)
                leave_minute = int(leave_minute)

                # Create time objects
                arrival_time = time(arrival_hour, arrival_minute)
                leave_time = time(leave_hour, leave_minute)

                print(f"Parsed Arrival Time: {arrival_time}, Leave Time: {leave_time}")

                # Calculate worked hours based on arrival and leave time
                worked_seconds = (datetime.combine(date.min, leave_time) - 
                                  datetime.combine(date.min, arrival_time)).seconds

                break_minutes = int(request.form.get('break_minutes', 0))
                allowable_break_minutes = 45
                extra_break_minutes = max(break_minutes - allowable_break_minutes, 0)
                worked_seconds -= (extra_break_minutes * 60)
                worked_hours = Decimal(max(worked_seconds, 0)) / Decimal(3600)
                print(f"Calculated Worked Hours: {worked_hours}")

                # Check for zero worked hours scenario
                if worked_hours <= 0:
                    worked_hours = Decimal(0)
                
            except ValueError as e:
                print(f"Error parsing times: {e}")
                flash("Invalid time input. Please provide valid numerical values.", 'danger')
                return redirect(url_for('index') + '?refresh=true' )

    today = datetime.now().date()

    try:
        # Ensure arrival_time and leave_time are correctly passed
        insert_attendance(employee_id, arrival_time, leave_time, is_absent, worked_hours, is_holiday, today)
        flash("Attendance submitted successfully!", 'success')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error in submit_attendance route: {e}")
        traceback.print_exc()
        flash("Failed to submit attendance. Please try again later.", 'danger')
        return redirect(url_for('index' )+ '?refresh=true')


@app.route('/calculate_salary')
def calculate_salary():
    try:
        today = datetime.now()
        current_year = today.year
        current_month = today.month
        # Get the current month and year
        today = datetime.now()
        month = today.month
        year = today.year

    
        table_name = f"attendance_{year}_{month:02d}"

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Fetch attendance data and join with employees table
     # Fetch attendance data and join with employees table for the current month only
        cursor.execute(f'''
        SELECT a.employee_id, e.basic_salary, SUM(a.worked_hours) AS total_hours, 
        COUNT(IF(a.is_absent = 1, 1, NULL)) AS total_absences
        FROM {table_name} a
        JOIN employees e ON a.employee_id = e.employee_id
        WHERE MONTH(a.date) = {current_month} AND YEAR(a.date) = {current_year}  -- Ensure only the current month is included
        GROUP BY a.employee_id, e.basic_salary
       ''')
        attendance_data = cursor.fetchall()

        salaries = []

        for record in attendance_data:
            employee_id = record['employee_id']
            basic_salary = Decimal(record['basic_salary']) if record['basic_salary'] is not None else Decimal(0)
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

    return render_template('salaries.html', salaries=salaries ,  current_year=current_year, 
                               current_month=current_month)


from datetime import datetime, timedelta
import calendar
import mysql.connector

def format_time(time_value):
    print(f"Time Value: {time_value}, Type: {type(time_value)}")  # Debug print
    if time_value is None:
        return 'N/A'
    elif isinstance(time_value, datetime):
        return time_value.strftime("%H:%M")
    elif isinstance(time_value, timedelta):
        total_seconds = int(time_value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    else:
        return 'N/A'


@app.route('/attendance_record/<int:employee_id>/<int:year>/<int:month>', endpoint='employee_attendance')
def attendance_record(employee_id, year, month):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        table_name = f"attendance_{year}_{month:02d}"
        
        # Check if table exists
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        if not cursor.fetchone():
            return f"Error: Table {table_name} does not exist.", 404

        # Fetch all records at once
        query = f"""
            SELECT 
                date, arrival_time, leave_time, is_absent, worked_hours, is_holiday
            FROM {table_name}
            WHERE employee_id = %s
        """
        cursor.execute(query, (employee_id,))
        records = {record["date"]: record for record in cursor.fetchall()}

        days_in_month = calendar.monthrange(year, month)[1]
        attendance_by_day = []

        for day in range(1, days_in_month + 1):
            current_date = datetime(year, month, day).date()
            record = records.get(current_date)

            attendance_by_day.append({
                'day': day,
                'date': current_date.strftime('%Y-%m-%d'),
                'arrival_time': format_time(record.get('arrival_time')) if record else 'N/A',
                'leave_time': format_time(record.get('leave_time')) if record else 'N/A',
                'is_absent': 'Yes' if record and record.get('is_absent') else 'No',
                'worked_hours': round(record.get('worked_hours', 0), 2) if record else 0,
                'is_holiday': 'Yes' if record and record.get('is_holiday') else 'No'
            })

        return render_template('attendance_record.html', attendance=attendance_by_day, year=year, month=month, employee_id=employee_id)

    except mysql.connector.Error as err:
        error_message = f"Database Error: {err}"
        traceback.print_exc()
        return abort(500, description=error_message)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        traceback.print_exc()
        return abort(500, description=error_message)
    finally:
        if conn.is_connected():
            conn.close()

@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if request.method == 'POST':
        name = request.form['name']
        position = request.form['position']
       
        
        try:
            # Connect to the MySQL database
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()

            # Insert the new employee into the 'employees' table
            cursor.execute('''
                INSERT INTO employees (name, position)
                VALUES (%s, %s)
            ''', (name, position))

            conn.commit()
            conn.close()
           
            # After adding employee, redirect to the employee list page with refresh parameter
            return redirect(url_for('list_employees')+ '?reload=true')

        except mysql.connector.Error as err:
            print(f"Error inserting employee: {err}")
            return "Error adding employee", 500

    return render_template('add_employee.html')



@app.route('/employees', methods=['GET'])
def list_employees():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Fetch all employees from the database
        cursor.execute('SELECT employee_id, name, position FROM employees')
        rows = cursor.fetchall()

        # Convert list of tuples to list of dictionaries
        employees = [{'employee_id': row[0], 'name': row[1], 'position': row[2]} for row in rows]

        conn.close()

        # Render the employee list template
        return render_template('employee_list.html', employees=employees )
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
       
        
        
        cursor.execute("""
            UPDATE employees
            SET name = %s, position = %s
            WHERE employee_id = %s
        """, (name, position, employee_id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('list_employees'))
    
    cursor.execute("SELECT * FROM employees WHERE employee_id = %s", (employee_id,))
    employee = cursor.fetchone()
    conn.close()
    return render_template('edit_employee.html', employee=employee)



from datetime import datetime
import mysql.connector

@app.route('/mark_holiday', methods=['POST'])
def mark_holiday():
    try:
        today = datetime.now().date()  # Get today's date
        month = today.month
        year = today.year
        table_name = f"attendance_{year}_{month:02d}"

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Check if holiday has already been marked for today
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE date = %s AND is_holiday = 1", (today,))
        holiday_exists = cursor.fetchone()[0]

        if holiday_exists > 0:
            conn.close()
            return "Holiday already marked for today.", 200  # Or a more appropriate message

        cursor.execute('SELECT employee_id FROM employees')
        employees = cursor.fetchall()

        for employee in employees:
            employee_id = employee[0] # Access employee_id correctly

            # Insert holiday record
            try:
                cursor.execute(f"""
                    INSERT INTO {table_name} (employee_id, arrival_time, leave_time, is_absent, worked_hours, date, is_holiday)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (employee_id, None, None, False, 9, today, 1)) 
                conn.commit()  
            except mysql.connector.IntegrityError:  
                print(f"Holiday already recorded for employee {employee_id} on {today}")
                conn.rollback() 
                continue 

        conn.close()
        return "Holiday marked successfully for all employees.", 200
    except mysql.connector.Error as err:
        print(f"Error marking holiday: {err}")
        if 'conn' in locals() and conn.is_connected(): 
            conn.close()
        return "Error marking holiday.", 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
        return "An unexpected error occurred.", 500



 
def get_current_month_table_name():
    today = datetime.now()
    month = today.month
    year = today.year
    return f"attendance_{year}_{month:02d}"

@app.route('/update_attendance', methods=['POST'])
def update_attendance():
    try:
        # Get form data
        employee_id = request.form.get('employee_id')
        date = request.form.get('date')
        arrival_time = request.form.get('arrival_time')
        leave_time = request.form.get('leave_time')
        worked_hours = request.form.get('worked_hours')
        is_absent = request.form.get('is_absent') == 'on'
        is_holiday = request.form.get('is_holiday') == 'on'

        # Convert times and worked hours
        arrival_time_obj = datetime.strptime(arrival_time, "%H:%M").time() if arrival_time else None
        leave_time_obj = datetime.strptime(leave_time, "%H:%M").time() if leave_time else None
        worked_hours = Decimal(worked_hours)

        # Database connection
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        year, month, _ = date.split('-')
        table_name = f"attendance_{year}_{month}"

        # Update query
        update_query = f"""
            UPDATE {table_name}
            SET arrival_time = %s, leave_time = %s, worked_hours = %s, is_absent = %s, is_holiday = %s
            WHERE employee_id = %s AND date = %s
        """
        cursor.execute(update_query, (arrival_time_obj, leave_time_obj, worked_hours, is_absent, is_holiday, employee_id, date))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": "Attendance updated successfully."})

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Failed to update attendance. Please try again."}), 400




db_pool = pooling.MySQLConnectionPool(pool_name="mypool",
                                      pool_size=5,
                                      **db_config)

@app.route('/search_employee')
def search_employee():
    connection = db_pool.get_connection()
    cursor = connection.cursor(dictionary=True)
    
    name = request.args.get('name', '').lower()
    if len(name) < 3:
        return jsonify([])

    query = "SELECT employee_id, name FROM employees WHERE name LIKE %s"
    cursor.execute(query, (f'%{name}%',))
    employees = cursor.fetchall()
    
    cursor.close()
    connection.close()

    return jsonify([{'id': emp['employee_id'], 'name': emp['name']} for emp in employees])

@app.route('/attendance_tables')
def attendance_tables():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Fetch all attendance tables
        cursor.execute("SHOW TABLES LIKE 'attendance_%'")
        tables = [table[0] for table in cursor.fetchall()]  # Get table names
        
        conn.close()
        
        return render_template('attendance_tables.html', tables=tables)
    
    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        return f"Database Error: {err}", 500
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return f"Unexpected Error: {e}", 500

@app.route('/attendance_table/<table_name>')
def view_attendance_table(table_name):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        query = f"SELECT * FROM {table_name}"
        cursor.execute(query)
        records = cursor.fetchall()

        conn.close()

        return render_template('view_attendance.html', table_name=table_name, records=records)

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        return f"Database Error: {err}", 500
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return f"Unexpected Error: {e}", 500

import calendar
from datetime import datetime


import calendar
from datetime import datetime

import calendar
from datetime import datetime

@app.route('/attendance/<int:employee_id>', methods=['GET'])
def yearly_attendance(employee_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Get the current year dynamically
        current_year = datetime.now().year  # Example: 2025

        attendance_by_month = {}

        for month in range(1, 13):  # Loop through January to December
            table_name = f"attendance_{current_year}_{month:02d}"  # Example: attendance_2025_01

            # Debugging: Print table being checked
            print(f"Checking table: {table_name}")

            # Check if table exists
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            if not cursor.fetchone():
                print(f"Table {table_name} does NOT exist")
                attendance_by_month[f"{calendar.month_name[month]}"] = "No attendance data available for this month."
                continue  # Skip to next month

            # Fetch attendance records for this employee
            query = f"""
                SELECT date, arrival_time, leave_time, is_absent, worked_hours, is_holiday
                FROM {table_name}
                WHERE employee_id = %s
            """
            cursor.execute(query, (employee_id,))
            records = cursor.fetchall()

            # Calculate total worked hours for the month
            if records:
                total_worked_hours = sum(record['worked_hours'] for record in records if record['worked_hours'] is not None)
                attendance_by_month[f"{calendar.month_name[month]}"] = {
                    "records": records,
                    "total_worked_hours": total_worked_hours
                }
            else:
                attendance_by_month[f"{calendar.month_name[month]}"] = "No attendance data available for this month."

            # Debugging: Print fetched data
            print(f"Month: {calendar.month_name[month]}, Records: {records}, Total Worked Hours: {total_worked_hours if records else 'N/A'}")

        conn.close()

        return render_template('yearly_attendance.html', employee_id=employee_id, year=current_year, attendance_by_month=attendance_by_month)

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        return "Error fetching attendance records", 500


if __name__ == '__main__':
    initialize()
    app.run(debug=True)
