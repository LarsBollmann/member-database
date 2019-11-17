from flask import (
    Blueprint, render_template, abort, flash, redirect, url_for, jsonify, current_app,
)
from wtforms.fields import StringField
from wtforms.validators import DataRequired
from wtforms.fields.html5 import EmailField
from itsdangerous import URLSafeSerializer, BadData
from flask_babel import _
from jsonschema import validate, ValidationError

from ..models import db, Person, as_dict
from ..utils import get_or_create, ext_url_for
from ..mail import send_email

from .models import Event, EventRegistration
from .json_forms import create_wtf_form


events = Blueprint('events', __name__, template_folder='templates')


@events.route('/<int:event_id>/registration/', methods=['GET', 'POST'])
def registration(event_id):
    event = Event.query.filter_by(id=event_id).first()
    if event is None:
        abort(404)

    if not event.registration_open:
        flash(f'Eine Anmeldung für "{event.name}" is derzeit nicht möglich', 'danger')
        return redirect(url_for('index'))

    form = create_wtf_form(
        event.registration_schema,
        additional_fields={
            'name': StringField('Name', [DataRequired()]),
            'email': EmailField('Email', [DataRequired()])
        }
    )

    if form.validate_on_submit():
        data = form.data
        email = data.pop('email')
        data.pop('csrf_token')

        try:
            validate(data, event.registration_schema)
        except ValidationError as e:
            flash(e.message, 'danger')
            return render_template('registration.html', form=form, event=event)

        person, new_person = get_or_create(
            Person,
            email=email,
            defaults={'name': data['name']}
        )

        registration, new = get_or_create(
            EventRegistration,
            person_id=person.id,
            event_id=event.id,
            defaults={'data': data, 'status': 'pending'},
        )

        if not new:
            if registration.status == 'pending':
                flash(
                    'Du hast bereits eine Anmeldung für diese Veranstaltung abgeschickt aber die Anmeldung nocht nicht bestätigt.'
                    ' Bitte klicke auf den Link in der Bestätigungsmail',
                    category='danger'
                )
            elif registration.status == 'registered':
                flash('Du bist bereits angemeldet. Falls du deine Daten ändern möchtest, klicke auf den Link in der Bestätigungsmail', category='danger')
        else:
            flash('Um deine Registrierung abzuschließen, klicke auf den Bestätigungslink in der Email, die wir dir geschickt haben! Erst dann bist du angemeldet.', category='success')

            db.session.commit()

            ts = URLSafeSerializer(
                current_app.config["SECRET_KEY"],
                salt='registration-key',
            )
            token = ts.dumps(
                (person.id, registration.id),
            )
            send_email(
                subject=_('Bestätige deine Anmeldung zu "{}"'.format(event.name)),
                sender=current_app.config['MAIL_SENDER'],
                recipients=[person.email],
                body=render_template(
                    'confirmation.txt',
                    name=person.name,
                    event=event.name,
                    confirmation_link=ext_url_for('events.confirmation', token=token),
                    submit_url=url_for('events.registration', event_id=event_id)
                )
            )

        return redirect(url_for('index'))

    return render_template(
        'registration.html',
        form=form, event=event,
    )


@events.route('/<int:event_id>/')
def get_event(event_id):
    event = Event.query.filter_by(id=event_id).first()
    if event is None:
        return jsonify(status='No such event'), 404

    return jsonify(
        status='success',
        event=as_dict(event),
    )


@events.route('/registration/<token>/', methods=['GET', 'POST'])
def confirmation(token):
    ts = URLSafeSerializer(
        current_app.config["SECRET_KEY"],
        salt='registration-key',
    )
    try:
        person_id, registration_id = ts.loads(token)
    except BadData as e:
        print(e)
        abort(404)

    person = Person.query.get(person_id)
    registration = EventRegistration.query.get(registration_id)

    if registration.status == 'pending':
        registration.status = 'confirmed'
        db.session.add(registration)
        flash('Deine Anmeldung ist jetzt bestätigt', 'success')
        send_email(
            subject=_('Anmeldung bestätigt: "{}"'.format(registration.event.name)),
            sender=current_app.config['MAIL_SENDER'],
            recipients=[person.email],
            body=render_template(
                'confirmed.txt',
                name=person.name,
                event=registration.event.name,
                edit_link=ext_url_for('events.confirmation', token=token),
            )
        )

    form = create_wtf_form(
        registration.event.registration_schema,
        additional_fields={
            'name': StringField('Name', [DataRequired()]),
            'email': EmailField('Email', [DataRequired()], render_kw={'disabled': ''})
        },
        data={**registration.data, 'email': person.email},
    )
    if form.validate_on_submit():
        data = form.data
        for key in ('email', 'csrf_token'):
            data.pop(key)

        registration.data = data
        flash('Anmeldung aktualisiert', 'success')

    db.session.commit()

    return render_template(
        'registration.html',
        form=form,
        event=registration.event,
        submit_url=url_for('events.confirmation', token=token)
    )
