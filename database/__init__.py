from flask import Flask, request
from flask_migrate import Migrate
from flask_bootstrap import Bootstrap
from flask_babel import Babel


from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlite3 import Connection as SQLite3Connection

from .config import Config
from .models import db
from .authentication import login
from .mail import mail
from .errors import not_found_error, internal_error, email_logger, unauthorized_error
from .events import events
from .main import main


@event.listens_for(Engine, 'connect')
def pragma_on_connect(dbapi_con, con_record):
    '''
    Make sure sqlite uses foreing key constraints
    https://stackoverflow.com/a/15542046/3838691
    '''
    if isinstance(dbapi_con, SQLite3Connection):
        cursor = dbapi_con.cursor()
        cursor.execute('PRAGMA foreign_keys = ON;')
        cursor.close()


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    mail.init_app(app)
    login.init_app(app)
    Migrate(app, db)
    Bootstrap(app)
    babel = Babel(app)

    @babel.localeselector
    def get_locale():
        return request.accept_languages.best_match(app.config['LANGUAGES'])

    app.register_blueprint(main)
    app.register_blueprint(events, url_prefix='/events')

    app.register_error_handler(401, unauthorized_error)
    app.register_error_handler(404, not_found_error)
    app.register_error_handler(500, internal_error)
    email_logger(app)

    return app
