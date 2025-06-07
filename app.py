from flask import Flask, render_template, url_for, session, redirect, flash
from auth_bp import auth
from resident_bp import resident
from secretary_bp import secretary
from treasurer_bp import treasurer
from helpers import set_inactive_last_login
# =================================== APP INSTANCES =================================== 
app = Flask(__name__)
app.secret_key = 'secret'
app.register_blueprint(auth, url_prefix='/au')
app.register_blueprint(resident, url_prefix='/resident')
app.register_blueprint(secretary, url_prefix='/secretary')
app.register_blueprint(treasurer, url_prefix='/treasurer')

@app.route('/')
def landing_page():
    if 'id' in session and 'role' in session:
        return redirect(url_for(f'{session["role"]}.dashboard'))
    return render_template('landing.html')


if __name__ == '__main__':
    app.run(debug=True)