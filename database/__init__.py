from flask import Flask, jsonify, request, url_for, render_template, redirect, flash
from flask_migrate import Migrate
from flask_mail import Mail, Message
from flask_login import current_user, login_user, logout_user, login_required
from itsdangerous import URLSafeTimedSerializer
from functools import partial

from sqlalchemy.exc import IntegrityError


from .config import Config
from .models import db, Person, User, as_dict
from .utils import get_or_create
from .authentication import login, LoginForm
from .mail import mail, send_email


app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
mail.init_app(app)
login.init_app(app)
migrate = Migrate(app, db)

ts = URLSafeTimedSerializer(app.config["SECRET_KEY"])


ext_url_for = partial(
    url_for,
    _external=True,
    _scheme='https' if app.config['USE_HTTPS'] else 'http',
)


@app.route('/')
def index():
    return render_template('base.html')


@app.route('/persons', methods=['GET'])
def get_persons():
    persons = [as_dict(person) for person in Person.query.all()]
    return jsonify(status='success', persons=persons)


@app.route('/persons', methods=['POST'])
def add_person():
    '''
    Add a new person via a http post request using a json payload
    that has name and email.
    '''
    data = request.get_json()

    try:
        p = Person(name=data['name'], email=data['email'])
        db.session.add(p)
        db.session.commit()
    except KeyError as e:
        return jsonify(
            status='error',
            message='Missing required parameter {}'.format(e.args[0])
        ), 422
    except IntegrityError:
        return jsonify(
            status='error',
            message='Person already exists',
        ), 422

    return jsonify(status='success')


@app.route('/members', methods=['GET'])
def get_members():
    '''Return a json list with all current members'''
    members = Person.query.filter_by(member=True, member_approved=True).all()
    persons = [as_dict(member) for member in members]
    return jsonify(status='success', persons=persons)


@app.route('/members', methods=['POST'])
def add_member():
    '''
    Create a new Person or find an existing one by email
    and set it's member attribute to True.
    Send an email to the board to notify them of a new membership application.
    '''
    data = request.get_json()

    try:
        p, new = get_or_create(
            Person,
            email=data['email'],
            defaults={'name': data['name']}
        )
    except KeyError as e:
        return jsonify(
            status='error',
            message='Missing required parameter {}'.format(e.args[0])
        ), 422

    if p.member:
        return jsonify(status='error', message='Already member'), 422

    p.member = True
    db.session.add(p)
    db.session.commit()

    send_email(
        subject='Neuer Mitgliedsantrag',
        sender=app.config['MAIL_SENDER'],
        recipients=[app.config['APPROVE_MAIL']],
        body=render_template(
            'mail/approve_member.txt',
            new_member=p,
            url=ext_url_for('applications'),
        )
    )

    return jsonify(status='success')


@app.route('/request_edit', methods=['POST'])
def send_edit_token():
    '''
    Request a link to edit personal data
    '''
    email = request.form['email']

    p = Person.query.filter_by(email=email).first()
    if p is None:
        return jsonify(status='error', message='No such person'), 422

    token = ts.dumps(email, salt='edit-key')

    send_email(
        subject='PeP et al. e.V. Mitgliedsdatenänderung',
        sender=app.config['MAIL_SENDER'],
        recipients=[email],
        body=render_template(
            'mail/edit_mail.txt',
            edit_link=ext_url_for('edit', token=token),
        )
    )

    return jsonify(status='success', message='Edit mail sent.')


@app.route('/edit/<token>')
def edit(token):
    pass


@app.route('/edit/<token>', methods=['POST'])
def save_edit(token):
    pass


@app.route('/applications')
@login_required
def applications():
    applications = Person.query.filter_by(member=True, member_approved=False).all()
    return render_template('applications.html', applications=applications)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user_or_email = form.user_or_email.data
        user = User.query.filter(
            (User.username == user_or_email) | (Person.email == user_or_email)
        ).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid user or password')
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('index'))
    return render_template('login.html', title='Login', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))
