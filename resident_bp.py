from flask import Blueprint, session, redirect, url_for, render_template, request, flash, jsonify
from helpers import database as db, RealDictCursor, get_current_user_info, get_current_user_reports, get_all_updates, get_update_by_id, get_all_comments, get_active_admins, get_all_sanctions
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import json


resident = Blueprint('resident', __name__)

# =================================== MIDDLEWARE =================================== 
@resident.before_request
def restrict_to_resident():
    """
    Middleware to check if user is a resident and not under sanctions
    Redirects to login if unauthorized or under sanctions
    """
    if session.get('role') != 'resident':
        return redirect(url_for('auth.login'))
    
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check for active sanctions
        cursor.execute("""
            SELECT * FROM sanctions 
            WHERE resident_id = %s 
            AND expires_at > NOW()
        """, (session['id'],))
        sanction = cursor.fetchone()
        
        if sanction:
            session.clear()
            flash(f'You are currently under sanctions for the Reason:"{sanction["reason"]}" until {sanction["expires_at"].strftime("%B %d, %Y %I:%M %p")}', 'danger')
            return redirect(url_for('auth.login'))
    except Exception as e:
        flash('An error occurred while checking sanctions', 'danger')
        print(f"Sanction check error: {e}")
        return redirect(url_for('auth.login'))
    finally:
        if conn:
            db.putconn(conn)

# =================================== ROUTES =================================== 
@resident.route('/dashboard')
def dashboard():
    """Render dashboard with user info, reports, updates and requests"""
    try:
        latest_update = get_all_updates()
        resident = get_current_user_info()
        active_admins = get_active_admins()

        # Set greeting based on time of day
        current_hour = datetime.now().hour
        greeting = 'Good Morning' if current_hour < 12 else 'Good Afternoon' if current_hour < 18 else 'Good Evening'

        return render_template('resident/dashboard.html', 
                            resident=resident,  
                            latest_update=latest_update, 
                            greeting=greeting, 
                            active_admins=active_admins)
    except Exception as e:
        flash('Error loading dashboard', 'danger')
        print(f"Dashboard error: {e}")
        return redirect(url_for('auth.login'))

@resident.route('/request')
def request_page():
    """Render document request page"""
    return render_template('resident/request.html')

@resident.route('/my-request')
def my_request():
    """Render user's requests with optional filtering"""
    try:
        resident = get_current_user_info()
        filter = request.args.get('filter', 'Default')
        my_request = get_my_requests(filter)
        return render_template('resident/my_request.html', my_request=my_request, resident=resident)
    except Exception as e:
        flash('Error loading requests', 'danger')
        print(f"My request error: {e}")
        return redirect(url_for('resident.dashboard'))

@resident.route('/reports')
def report_page():
    """Render user's reports page"""
    try:
        reports = get_current_user_reports()
        resident = get_current_user_info()
        return render_template('resident/report.html', reports=reports, resident=resident)
    except Exception as e:
        flash('Error loading reports', 'danger')
        print(f"Reports error: {e}")
        return redirect(url_for('resident.dashboard'))

@resident.route('/updates')
def updates():
    """Render community updates page"""
    try:
        all_updates = get_all_updates()
        all_comments = get_all_comments()
        return render_template('resident/updates.html', all_updates=all_updates, all_comments=all_comments)
    except Exception as e:
        flash('Error loading updates', 'danger')
        print(f"Updates error: {e}")
        return redirect(url_for('resident.dashboard'))

@resident.route('/comments/<int:update_id>')
def comments(update_id):
    """Render comments for a specific update"""
    try:
        current_update, comments = get_update_by_id(update_id)
        return render_template('resident/comments.html', current_update=current_update, comments=comments)
    except Exception as e:
        flash('Error loading comments', 'danger')
        print(f"Comments error: {e}")
        return redirect(url_for('resident.updates'))

@resident.route('/account')
def account():
    """Render user account page"""
    try:
        current_user = get_current_user_info()
        return render_template('resident/account.html', current_user=current_user)
    except Exception as e:
        flash('Error loading account', 'danger')
        print(f"Account error: {e}")
        return redirect(url_for('resident.dashboard'))

@resident.route('/about')
def about():
    """Render about page"""
    return render_template('resident/about.html')


# =================================== FORM SUBMISSIONS =================================== 
@resident.route('/report-submit', methods=['POST'])
def report_submit():
    """Handle report submission"""
    if request.method != 'POST':
        return redirect(url_for('resident.report_page'))

    try:
        title = request.form['report-title']
        category = request.form['report-category']
        content = request.form['report-description']
        resident_id = session['id']
        
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            INSERT INTO community_report (resident_id, title, content, category) 
            VALUES (%s, %s, %s, %s)
        """, (resident_id, title, content, category))
        conn.commit()
        
        flash('Report submitted successfully!', 'success')
        return redirect(url_for('resident.report_page'))
    except Exception as e:
        flash('An error occurred while submitting your report', 'danger')
        print(f"Report submission error: {e}")
        return redirect(url_for('resident.report_page'))
    finally:
        if conn:
            db.putconn(conn)

@resident.route('/report-delete', methods=['POST'])
def report_delete():
    """Handle report deletion"""
    if request.method != 'POST':
        return redirect(url_for('resident.report_page'))

    report_id = request.form.get('report-id')
    if not report_id:
        flash('Invalid report ID', 'danger')
        return redirect(url_for('resident.report_page'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("DELETE FROM community_report WHERE id = %s", (report_id,))
        conn.commit()
        flash('Report deleted successfully!', 'success')
    except Exception as e:
        flash('An error occurred while deleting your report', 'danger')
        print(f"Report deletion error: {e}")
    finally:
        if conn:
            db.putconn(conn)
    return redirect(url_for('resident.report_page'))

@resident.route('/request-submit', methods=['POST'])
def request_submit():
    """Handle document request submission"""
    if request.method != 'POST':
        return redirect(url_for('resident.request_page'))

    try:
        document_type = request.form['document-type']
        resident_id = session['id']
        
        # Create uploads directory
        upload_dir = os.path.join('static', 'uploads', 'documents', str(resident_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        # Handle requirements based on document type
        requirements = {}
        if document_type != 'indigency-certificate':
            for file_key in request.files:
                file = request.files[file_key]
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    file_path = os.path.join(upload_dir, filename)
                    file.save(file_path)
                    requirements[file_key] = os.path.join('uploads', 'documents', str(resident_id), filename)
        else:
            requirements['purpose'] = request.form.get('purpose', '')
        
        # Get document price
        prices = {
            'barangay-clearance': 50,
            'certificate-of-residency': 50,
            'business-permit': 200,
            'indigency-certificate': 0
        }
        price = prices.get(document_type, 0)
        
        # Save to database
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            INSERT INTO request_document 
            (resident_id, document_type, price, requirements)
            VALUES (%s, %s, %s, %s)
        """, (resident_id, document_type, price, json.dumps(requirements)))
        conn.commit()
        
        flash('Document request submitted successfully!', 'success')
        return redirect(url_for('resident.my_request'))
    except Exception as e:
        flash('An error occurred while submitting your request', 'danger')
        print(f"Request submission error: {e}")
        return redirect(url_for('resident.request_page'))
    finally:
        if conn:
            db.putconn(conn)

@resident.route('/vote-update', methods=['POST'])
def vote_update():
    """Handle voting on community updates"""
    if request.method != 'POST':
        return redirect(url_for('resident.updates'))

    update_id = request.form.get('update_id')
    vote = request.form.get('vote')
    source_page = request.form.get('source_page', 'updates')

    if not update_id or not vote:
        flash('Invalid vote parameters', 'danger')
        return redirect(url_for('resident.updates'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Handle different vote types
        vote_queries = {
            'add_up_vote': [
                "UPDATE community_update SET up_vote = up_vote || %s::jsonb WHERE id = %s",
                "UPDATE community_update SET down_vote = COALESCE((SELECT jsonb_agg(value) FROM jsonb_array_elements_text(down_vote) AS elem(value) WHERE value::int != %s), '[]'::jsonb) WHERE id = %s"
            ],
            'remove_up_vote': [
                "UPDATE community_update SET up_vote = COALESCE((SELECT jsonb_agg(value) FROM jsonb_array_elements_text(up_vote) AS elem(value) WHERE value::int != %s), '[]'::jsonb) WHERE id = %s"
            ],
            'add_down_vote': [
                "UPDATE community_update SET down_vote = down_vote || %s::jsonb WHERE id = %s",
                "UPDATE community_update SET up_vote = COALESCE((SELECT jsonb_agg(value) FROM jsonb_array_elements_text(up_vote) AS elem(value) WHERE value::int != %s), '[]'::jsonb) WHERE id = %s"
            ],
            'remove_down_vote': [
                "UPDATE community_update SET down_vote = COALESCE((SELECT jsonb_agg(value) FROM jsonb_array_elements_text(down_vote) AS elem(value) WHERE value::int != %s), '[]'::jsonb) WHERE id = %s"
            ]
        }

        if vote in vote_queries:
            for query in vote_queries[vote]:
                cursor.execute(query, (session['id'], update_id))
            conn.commit()
            flash('Vote recorded successfully', 'success')
        else:
            flash('Invalid vote type', 'danger')

    except Exception as e:
        flash('An error occurred while processing your vote', 'danger')
        print(f"Vote error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('resident.comments', update_id=update_id) if source_page == 'comments' else url_for('resident.updates'))

@resident.route('/comment-update', methods=['POST'])
def comment_update():
    """Handle comment submission and deletion"""
    if request.method != 'POST':
        return redirect(url_for('resident.updates'))

    submit_type = request.form.get('submit_type')
    post_id = request.form.get('post_id')

    if not submit_type or not post_id:
        flash('Invalid comment parameters', 'danger')
        return redirect(url_for('resident.updates'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        if submit_type == 'add_comment':
            comment = request.form.get('comment')
            if not comment:
                flash('Comment cannot be empty', 'danger')
                return redirect(url_for('resident.comments', update_id=post_id))

            cursor.execute("""
                INSERT INTO comments (post_id, created_by, content) 
                VALUES (%s, %s, %s)
            """, (post_id, session['id'], comment))
            flash('Comment added successfully', 'success')

        elif submit_type == 'delete_comment':
            comment_id = request.form.get('comment_id')
            if not comment_id:
                flash('Invalid comment ID', 'danger')
                return redirect(url_for('resident.comments', update_id=post_id))

            cursor.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
            flash('Comment deleted successfully', 'success')

        conn.commit()
    except Exception as e:
        flash('An error occurred while processing your comment', 'danger')
        print(f"Comment error: {e}")
    finally:
        if conn:
            db.putconn(conn)

    return redirect(url_for('resident.comments', update_id=post_id))

@resident.route('/delete-request', methods=['POST'])
def delete_request():
    """Handle document request deletion"""
    if request.method != 'POST':
        return redirect(url_for('resident.my_request'))

    request_id = request.form.get('request_id')
    if not request_id:
        flash('Invalid request ID', 'danger')
        return redirect(url_for('resident.my_request'))

    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("DELETE FROM request_document WHERE id = %s", (request_id,))
        conn.commit()
        flash('Request deleted successfully!', 'success')
    except Exception as e:
        flash('An error occurred while deleting your request', 'danger')
        print(f"Request deletion error: {e}")
    finally:
        if conn:
            db.putconn(conn)
    return redirect(url_for('resident.my_request'))

# =================================== HELPER FUNCTIONS =================================== 
def get_my_requests(filter='Default'):
    """Get user's document requests with optional filtering"""
    conn = None
    try:
        conn = db.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        if filter == 'Default':
            cursor.execute("""
                SELECT request_document.*, secretary.username 
                FROM request_document 
                LEFT JOIN secretary ON request_document.reviewed_by = secretary.id 
                WHERE resident_id = %s 
                ORDER BY created_at DESC
            """, (session['id'],))
        else:
            cursor.execute("""
                SELECT request_document.*, secretary.username 
                FROM request_document 
                LEFT JOIN secretary ON request_document.reviewed_by = secretary.id 
                WHERE resident_id = %s AND request_document.status = %s 
                ORDER BY created_at DESC
            """, (session['id'], filter))
        
        return cursor.fetchall()
    except Exception as e:
        print(f"Error fetching requests: {e}")
        return []
    finally:
        if conn:
            db.putconn(conn)

    
