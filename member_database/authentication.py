from flask_login import LoginManager, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo
from flask import (
    redirect, url_for, request, flash, abort, jsonify, current_app,
    render_template
)
from itsdangerous import URLSafeTimedSerializer
import base64
from functools import wraps

from .models import User
from .mail import send_email
from .utils import ext_url_for


login = LoginManager()


def access_required(name):
    '''
    Check if current_user has a role with access_level named `name`.
    Abort request with 401, if that's not the case.

    Usage:
        Decorate view function (`app.route(...)`) with this decorator and
        specify a name of an access_level. The name will be compared to
        all access_levels of all rules of the current_user.
    '''
    def access_decorator(func):
        @wraps(func)
        @login_required  # first of all a use needs to be logged in
        def decorated_function(*args, **kwargs):
            if not current_user.has_access(name):
                abort(401)

            return func(*args, **kwargs)
        return decorated_function
    return access_decorator


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


@login.request_loader
def load_user_from_request(request):

    basic_auth = request.headers.get('Authorization')

    if basic_auth:
        basic_auth = basic_auth.replace('Basic ', '', 1)
        try:
            basic_auth = base64.b64decode(basic_auth)
            user, password = basic_auth.decode().split(':')
        except (TypeError, ValueError):
            # a failed attempt should take as long
            # as a successfull one, thus we do not exit early
            # but perform the database request anyway
            user = None
            password = ''

        user = User.query.filter_by(username=user).first()

        if user and user.check_password(password) is True:
            return user

    return None


@login.unauthorized_handler
def handle_needs_login():
    if 'application/json' in request.headers.get('Accept'):
        return jsonify(status='access_denied'), 401

    if request.headers.get('Authorization') is not None:
        abort(401)

    flash("You have to be logged in to access this page.", category='danger')
    return redirect(url_for('main.login_page', next=request.full_path))


class LoginForm(FlaskForm):
    user_or_email = StringField('Username/Email', validators=[DataRequired()])
    password = PasswordField('Passwort', validators=[DataRequired()])
    submit = SubmitField('Login')


class SendPasswordResetForm(FlaskForm):
    user_or_email = StringField('Username/Email', validators=[DataRequired()])
    submit = SubmitField('Send password reset email')


class PasswordResetForm(FlaskForm):
    new_password = PasswordField(
        'New password',
        validators=[
            DataRequired(),
            EqualTo('confirm', message='Passwords must match')
        ]
    )
    confirm = PasswordField('Confirm password', validators=[DataRequired()])
    submit = SubmitField('Reset password')


def send_password_reset_mail(person):
    ts = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    token = ts.dumps(person.email, salt='password-reset')

    link = ext_url_for('main.reset_password', token=token)

    send_email(
        subject='Password reset for registration.pep-dortmund.org',
        recipients=[f'{person.name} <{person.email}>'],
        sender=current_app.config['MAIL_SENDER'],
        body=render_template('mail/reset_password.html', reset_link=link)
    )


def load_reset_token(token):
    ts = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return ts.loads(token, salt='password-reset', max_age=10 * 60)
