from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from helpers import database as db, RealDictCursor, get_all_resident_info
from bcrypt import hashpw, checkpw, gensalt
from datetime import datetime, date, timedelta
from collections import defaultdict

treasurer = Blueprint('treasurer', __name__)

# =================================== MIDDLEWARE ===================================
@treasurer.before_request
def restrict_to_treasurer():
    """Middleware to ensure only treasurer can access these routes"""
    if session.get('role') != 'treasurer':
        return redirect(url_for('auth.login'))

# =================================== ROUTES ===================================
@treasurer.route('/dashboard')
def dashboard():
    """Render treasurer dashboard with collections and recent payments"""
    try:
        collections, pending = get_all_collections()
        active_residents = get_all_resident_info('Online')
        recent_payments = get_recent_payments(8)
        return render_template('treasurer/dashboard.html', 
                             collections=collections, 
                             pending=pending, 
                             active_residents=active_residents, 
                             recent_payments=recent_payments)
    except Exception as e:
        flash('Error loading dashboard', 'danger')
        print(f"Dashboard error: {e}")
        return redirect(url_for('auth.login'))

@treasurer.route('/financial-reports')
def financial_reports_treas():
    """Render financial reports with optional date filtering"""
    try:
        # Get query params
        report_type = request.args.get('report_type', 'monthly')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Set default date range based on report type
        today = date.today()
        if not start_date or not end_date:
            start_date, end_date = get_default_date_range(today, report_type)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        # Get financial data
        total_income, income_breakdown = get_financial_data(start_date, end_date)

        return render_template(
            'treasurer/financial_reports.html',
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            total_income=f"{total_income:,.2f}",
            income_breakdown=income_breakdown
        )
    except Exception as e:
        flash('Error loading financial reports', 'danger')
        print(f"Financial reports error: {e}")
        return redirect(url_for('treasurer.dashboard'))

@treasurer.route('/receipts')
def receipts_treas():
    """Render receipts page with pending payments"""
    try:
        pending = get_all_pending_receipts()
        return render_template('treasurer/receipts.html', pending=pending)
    except Exception as e:
        flash('Error loading receipts', 'danger')
        print(f"Receipts error: {e}")
        return redirect(url_for('treasurer.dashboard'))

@treasurer.route('/account')
def account_treas():
    """Render treasurer account page"""
    return render_template('treasurer/account.html')

# =================================== FORM SUBMISSIONS ===================================
@treasurer.route('/mark-paid', methods=['POST'])
def mark_paid():
    """Handle marking a receipt as paid"""
    if request.method != 'POST':
        return redirect(url_for('treasurer.receipts_treas'))

    request_id = request.form.get('request_id')
    if not request_id:
        flash('Invalid request ID', 'danger')
        return redirect(url_for('treasurer.receipts_treas'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            UPDATE receipt 
            SET payment_status = 'Paid', paid_at = NOW(), issued_by = %s 
            WHERE request_id = %s
        """, (session.get('id'), request_id))
        conn.commit()
        flash('Payment marked as paid successfully', 'success')
    except Exception as e:
        flash('Error marking payment as paid', 'danger')
        print(f"Mark paid error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('treasurer.receipts_treas'))

@treasurer.route('/mark-released', methods=['POST'])
def mark_released():
    """Handle marking a document as released"""
    if request.method != 'POST':
        return redirect(url_for('treasurer.receipts_treas'))

    request_id = request.form.get('request_id')
    if not request_id:
        flash('Invalid request ID', 'danger')
        return redirect(url_for('treasurer.receipts_treas'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Update document status
        cursor.execute("""
            UPDATE request_document 
            SET status = 'Released' 
            WHERE id = %s
        """, (request_id,))
        
        # Update receipt
        cursor.execute("""
            UPDATE receipt 
            SET issued_by = %s 
            WHERE request_id = %s
        """, (session.get('id'), request_id))
        
        conn.commit()
        flash('Document marked as released successfully', 'success')
    except Exception as e:
        flash('Error marking document as released', 'danger')
        print(f"Mark released error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('treasurer.receipts_treas'))

# =================================== HELPER FUNCTIONS ===================================
def get_default_date_range(today, report_type):
    """Get default date range based on report type"""
    if report_type == 'monthly':
        start_date = today.replace(day=1)
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(days=1)
    elif report_type == 'quarterly':
        quarter = (today.month - 1) // 3 + 1
        start_month = 3 * (quarter - 1) + 1
        start_date = date(today.year, start_month, 1)
        if start_month + 3 > 12:
            end_date = date(today.year, 12, 31)
        else:
            end_date = date(today.year, start_month + 3, 1) - timedelta(days=1)
    elif report_type == 'annual':
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
    else:
        start_date = today.replace(day=1)
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(days=1)
    
    return start_date, end_date

def get_financial_data(start_date, end_date):
    """Get financial data for the specified date range"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all paid documents in date range
        cursor.execute("""
            SELECT rd.document_type, rd.price
            FROM request_document rd
            JOIN receipt r ON r.request_id = rd.id
            WHERE r.paid_at IS NOT NULL
            AND r.paid_at::date BETWEEN %s AND %s
        """, (start_date, end_date))
        rows = cursor.fetchall()

        # Calculate total income and breakdown
        total_income = sum(row['price'] for row in rows)
        breakdown = defaultdict(float)
        for row in rows:
            breakdown[row['document_type']] += row['price']

        # Format breakdown data
        income_breakdown = []
        for doc_type, amount in breakdown.items():
            percent = (amount / total_income * 100) if total_income else 0
            income_breakdown.append({
                'category': doc_type.replace('_', ' ').title(),
                'amount': f"{amount:,.2f}",
                'percent': f"{percent:.2f}"
            })

        # Sort by amount descending
        income_breakdown.sort(key=lambda x: float(x['amount'].replace(',', '')), reverse=True)
        
        return total_income, income_breakdown
    except Exception as e:
        print(f"Error getting financial data: {e}")
        return 0, []
    finally:
        if conn:
            db.putconn(conn)

def get_all_collections():
    """Get total collections and pending amounts"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get released collections
        cursor.execute("""
            SELECT SUM(price) as sum 
            FROM request_document 
            WHERE status = 'Released'
        """)
        collections = cursor.fetchone()
        
        # Get pending collections
        cursor.execute("""
            SELECT SUM(price) as sum 
            FROM request_document 
            WHERE status = 'To Pay'
        """)
        pending = cursor.fetchone()
        
        return collections, pending
    except Exception as e:
        print(f"Error getting collections: {e}")
        return {'sum': 0}, {'sum': 0}
    finally:
        if conn:
            db.putconn(conn)

def get_all_pending_receipts():
    """Get all pending receipts with resident information"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT 
                request_document.*, 
                CONCAT(first_name, ' ', last_name) as resident_name, 
                receipt.* 
            FROM receipt 
            LEFT JOIN request_document ON receipt.request_id = request_document.id 
            LEFT JOIN resident ON request_document.resident_id = resident.id 
            WHERE request_document.status IN ('To Pay', 'Released', 'To Pick Up')
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting pending receipts: {e}")
        return []
    finally:
        if conn:
            db.putconn(conn)

def get_recent_payments(hours=8):
    """Get recent payments within specified hours"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT 
                r.paid_at, 
                rd.price, 
                rd.document_type, 
                CONCAT(res.first_name, ' ', res.last_name) as resident_name
            FROM receipt r
            JOIN request_document rd ON r.request_id = rd.id
            LEFT JOIN resident res ON rd.resident_id = res.id
            WHERE r.paid_at IS NOT NULL 
            AND r.paid_at >= NOW() - INTERVAL '%s hours'
            ORDER BY r.paid_at DESC
        """, (hours,))
        return cursor.fetchall()
    except Exception as e:
        print(f"Error getting recent payments: {e}")
        return []
    finally:
        if conn:
            db.putconn(conn)

# =================================== ADMIN FUNCTIONS ===================================
def add():
    """Admin function to add new treasurer accounts"""
    username = input("Enter username: ")
    email = input("Enter email: ")
    password = input("Enter password: ")

    if not all([username, email, password]):
        print("All fields are required")
        return

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        password_hash = hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')

        # Check for existing users
        roles = ['secretary', 'resident', 'treasurer']
        for role in roles:
            cursor.execute(f"SELECT * FROM {role} WHERE email = %s", (email,))
            if cursor.fetchone():
                print(f"User with email {email} already exists in {role} role")
                return

        # Add new treasurer
        cursor.execute("""
            INSERT INTO treasurer(email, password, username) 
            VALUES (%s, %s, %s)
        """, (email, password_hash, username))
        conn.commit()
        print("Treasurer account created successfully")
    except Exception as e:
        print(f"Error creating treasurer account: {e}")
    finally:
        if conn:
            db.putconn(conn)
# add()