from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from ..models import db, Person


def get_user_by_name_or_email(name_or_email):
    return (
        User.query.join(Person)
        .filter((User.username == name_or_email) | (Person.email == name_or_email))
        .one_or_none()
    )


roles = db.Table(
    "roles",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("role_id", db.String(32), db.ForeignKey("role.id"), primary_key=True),
)


access_levels = db.Table(
    "access_levels",
    db.Column(
        "role_id",
        db.String(32),
        db.ForeignKey("role.id"),
        primary_key=True,
    ),
    db.Column(
        "access_level_id",
        db.String(32),
        db.ForeignKey("access_level.id"),
        primary_key=True,
    ),
)


class AccessLevel(db.Model):
    id = db.Column(db.String(32), primary_key=True)


class Role(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    access_levels = db.relationship(
        "AccessLevel",
        secondary=access_levels,
        lazy="subquery",
        backref=db.backref("roles", lazy=True),
    )


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(128))

    person_id = db.Column(db.Integer, db.ForeignKey("person.id"), nullable=False)

    roles = db.relationship(
        "Role", secondary=roles, lazy="subquery", backref=db.backref("users", lazy=True)
    )

    person = db.relationship("Person", backref="user", lazy="subquery")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_access(self, name):
        for role in self.roles:
            if any([name == level.id for level in role.access_levels]):
                return True
        return False

    def __repr__(self):
        return f"<User {self.id}: {self.username}>"
