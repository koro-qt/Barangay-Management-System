from flask import Blueprint, render_template, url_for, redirect, session, request, flash
from bcrypt import checkpw, hashpw, gensalt
from helpers import database as db, RealDictCursor, get_current_user_info, set_active_last_login, set_inactive_last_login
from datetime import datetime

auth = Blueprint('auth', __name__)
roles = ['resident', 'secretary', 'treasurer']

# =================================== ROUTES =================================== 
@auth.route('/login')
def login():
    return redirect(url_for('landing_page'))

@auth.route('/register', methods=['GET'])
def register():
    return render_template('register.html')

@auth.route('/logout')
def logout():
    set_inactive_last_login()
    session.clear()
    return redirect(url_for('landing_page'))

# =================================== ROUTES WITH FUNCTIONS =================================== 
@auth.route('/login-submit', methods=['POST'])
def login_submit():
    email = request.form['email']
    password = request.form['password']
 
    user_found = False

    for role in roles:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"SELECT * FROM {role} WHERE email = %s", (email,))
        user = cursor.fetchone()
        db.putconn(conn)
        if user:
            user_found = True

            if role == 'resident':
                conn = db.getconn()
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("""
                    SELECT * FROM sanctions 
                    WHERE resident_id = %s 
                    AND expires_at > NOW()
                """, (user['id'],))
                sanction = cursor.fetchone()
                db.putconn(conn)

                if sanction:
                    flash(f'You are currently under sanctions for the Reason:"{sanction["reason"]}" until {sanction["expires_at"].strftime("%B %d, %Y %I:%M %p")}', 'danger')
                    return redirect(url_for('landing_page'))

            if checkpw(password.encode('utf-8'), user['password'].encode()):
                session['id'] = user['id']
                session['role'] = role
                set_active_last_login()
                return redirect(url_for(f'{role}.dashboard'))
            else:
                flash('Incorrect password', 'danger')
                return redirect(url_for('landing_page'))
    
    if not user_found:
        flash('Email does not exist', 'danger')
        return redirect(url_for('landing_page'))
    
    return redirect(url_for('landing_page'))

@auth.route('/register-submit', methods=['GET', 'POST'])
def register_submit():
    if request.method == 'POST':
        first_name = request.form['first-name'].title()
        last_name = request.form['last-name'].title()
        age = request.form['age']
        gender = request.form['gender']
        civil_status = request.form['civil-status']
        birth_date = request.form['birth-date']
        contact_number = request.form['contact-number']
        email = request.form['email'].lower()
        password = request.form['password']
        confirm_password = request.form['confirm-password']
        address = request.form['address'].title()
    
        if password == confirm_password:
            conn = None
            try:
                conn = db.getconn()
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Check if email exists within the same transaction
                for role in roles:
                    cursor.execute(f"SELECT email FROM {role} WHERE email = %s", (email,))
                    if cursor.fetchone():
                        flash('Email already exists. Please use a different email address.', 'danger')
                        return redirect(url_for('auth.register'))
                
                password_hash = hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')
                
                command = """
                    INSERT INTO resident 
                    (first_name, last_name, age, gender, birth_date, contact_number, civil_status, email, password, address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """    
                values = (first_name, last_name, age, gender, birth_date, contact_number, civil_status, email, password_hash, address)
                cursor.execute(command, values)
                conn.commit()
                db.putconn(conn)
                flash('Registration successful! You can now login.', 'success')
                return redirect(url_for('landing_page'))
                
            except Exception as error:
                if conn:
                    conn.rollback()
                print(error)
                flash('An error occurred during registration. Please try again.', 'danger')
                return redirect(url_for('auth.register'))
        else:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(url_for('auth.register'))
                    
    return redirect(url_for('auth.register'))


# =================================== CHECK FUNCTIONS =================================== 
def email_exist(email):
    conn = db.getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        # Check in all role tables
        for role in roles:
            cursor.execute(f"SELECT email FROM {role} WHERE email = %s", (email,))
            if cursor.fetchone():
                return True
        return False
    except Exception as error:
        print(error)
        return False
    finally:
        db.putconn(conn)


