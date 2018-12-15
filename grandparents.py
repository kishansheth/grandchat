import os
import time, datetime
import json, demjson
from google.oauth2 import service_account
from flask import Flask
from flask import flash
from flask import render_template
from flask_sqlalchemy import SQLAlchemy
from flask import url_for
from flask import request
from flask import redirect
from flask import session
from flask_login import LoginManager, login_user, UserMixin, login_required, logout_user, current_user
from sqlalchemy import desc
from flask_wtf import *
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from werkzeug.utils import secure_filename
from wtforms import Form, BooleanField, StringField, SubmitField, PasswordField, SelectField, validators
from wtforms.validators import ValidationError, DataRequired
from flask_socketio import SocketIO, send, emit
from google.cloud import translate

UPLOAD_FOLDER = '/uploads'
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.static_folder = 'static'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'

db = SQLAlchemy(app)
socketio = SocketIO(app)
app.secret_key = 'secret'

# supported languages
LANGUAGE_CHOICES = [('de', 'Deutsch'), ('en', 'English'), ('es', 'EspaÃ±ol'), ('fr', 'FranÃ§ais'), ('hi', 'हिंदी'), ('it', 'Italia'), ('pt', 'Português'), ('ko', '한국어'), ('cmn-Hans-CN', '普通话（简体)'), ('ja','日本人')]

# database setup

# many to many relationship
grandparent_grandchild = db.Table('grandparent_grandchild',
    db.Column('parent_child_id', db.Integer, primary_key=True),
    db.Column('grandchild_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('grandparent_id', db.Integer, db.ForeignKey('user.id'))
)

# User table
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30))
    password = db.Column(db.String(30))
    first_name = db.Column(db.String(30))
    last_name = db.Column(db.String(30))
    profile_picture = db.Column(db.String(1000))
    display_language = db.Column(db.String(20))
    spoken_language = db.Column(db.String(20))
    # messages = db.relationship('Message', backref='author')
    grandparent = db.Column(db.Boolean)

    # grandparents only
    advanced_user = db.Column(db.Boolean)

    # grandchildren only
    all_grandparents = db.relationship('User', secondary=grandparent_grandchild, primaryjoin=id == grandparent_grandchild.c.grandchild_id, secondaryjoin=id == grandparent_grandchild.c.grandparent_id, backref=db.backref('all_grandchildren', lazy='dynamic'))

# Message table
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime)
    body = db.Column(db.String(300))
    body_trans = db.Column(db.String(300))
    attachment = db.Column(db.String(1000))
    sender = db.Column(db.Integer, db.ForeignKey("user.id"))
    recipient = db.Column(db.Integer, db.ForeignKey("user.id"))
    likes = db.Column(db.Integer)

    sender_relationship = db.relationship("User", foreign_keys=[sender])
    recipient_relationship = db.relationship("User", foreign_keys=[recipient])

# login setup

login_manager = LoginManager()
login_manager.init_app(app)

class Grandchild_Registration(Form):
    first_name = StringField('', [validators.Length(min=2, max=30)], render_kw={"placeholder": "first name"})
    last_name = StringField('', [validators.Length(min=2, max=30)], render_kw={"placeholder": "last name"})
    username = StringField('', [validators.Length(min=4, max=25)], render_kw={"placeholder": "username"})
    password = PasswordField('', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords must match.')
    ], render_kw={"placeholder": "password"})
    confirm = PasswordField('', render_kw={"placeholder": "confirm password"})
    profile_picture = FileField('')
    profile = StringField('', [validators.Length(min=4, max=300)], render_kw={"placeholder": "profile pic url"})
    display_language = SelectField('Display Language', choices=LANGUAGE_CHOICES, default='en')
    spoken_language = SelectField('', choices=LANGUAGE_CHOICES, default='en')
    submit = SubmitField('Step 3: Add your grandparents.')

class LoginForm(Form):
    username = StringField('', [validators.Length(min=4, max=25)], render_kw={"placeholder": "username"})
    password = PasswordField('', [validators.DataRequired()], render_kw={"placeholder": "password"})

# search form
class UserSearchForm(Form):
    search = StringField('', [validators.Length(min=1)], render_kw={"placeholder": "search username"})

### SOCKETS ###

@socketio.on('message')
def handleMessage(data):
    # javascript to python object
    data_dict = demjson.decode(str(data))

    # create Message db entry
    timestamp = datetime.datetime.now()
    body = data_dict['msg']
    sender = current_user.id
    sender_lang = User.query.filter_by(id=sender).first().spoken_language
    recipient = int(data_dict['recipient'])
    recipient_lang = User.query.filter_by(id=recipient).first().spoken_language
    if sender_lang == recipient_lang:
        body_t = body
    else:
        body_t = translate_text(body, sender_lang, recipient_lang)
    message = Message(timestamp=timestamp, body=body, body_trans=body_t, sender=sender, recipient=recipient)
    
    # add entry to db
    db.session.add(message)
    db.session.commit()

    # add translation and convert back to javascript dict
    data_dict['msg_trans'] = body_t
    json_string = json.dumps(data_dict)
    json_obj = json.loads(json_string)

    emit('message', json_obj, broadcast = True)

### AUTOCOMPLETE ###

@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    return jsonify(json_list=[user.username for user in User.query.all()])

### LOGIN ###

@login_manager.user_loader
def load_user(user_id):
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return None
    return user

@app.route('/landing')
def landing():
    return render_template('twitter/landing.html')

@app.route('/register/grandparent', methods=('GET', 'POST'))
def register_grandparent():
    form = Grandchild_Registration(request.form)
    #if request.method == 'POST' and form.validate():
    if request.method == 'POST' and form.validate():
        print('validated')
        user = User()
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.username = form.username.data
        user.password = form.password.data
        user.grandparent = True

        print('first name: ', user.first_name)
        print('last name: ', user.last_name)
        print('username: ', user.username)
        
        print('doing profile pic')
        # profile pic
        user.profile_picture = form.profile.data
        # print('photo: ', photo)
        # filename = str(user.id) + '_profile'
        # print('filename: ', filename)
        # target = os.path.join(APP_ROOT, 'static/profile_pics')
        # print('target: ', target)
        # if not os.path.isdir(target):
        #     os.mkdir(target)
        # destination = "/".join([target, filename])
        # print('destination: ', destination)
        # photo.save(destination)
        # user.profile_picture = filename

        # language prefs
        user.display_language = form.display_language.data
        user.spoken_language = form.spoken_language.data

        # add user to database
        db.session.add(user)
        current_user.all_grandparents.append(user)
        db.session.commit()
        flash('Thanks for registering!')
        return redirect(url_for('manage'))
    return render_template('twitter/register.html', form=form, gp_registration=True)

@app.route('/register/manage', methods=('GET', 'POST'))
def manage():
    user_search = []
    form = UserSearchForm(request.form)
    if request.method == 'POST' and form.validate():
        user_search = User.query.filter((User.username.contains(form.search.data)) | (User.username.ilike(form.search.data)) | (User.first_name.ilike(form.search.data)) | (User.last_name.ilike(form.search.data))).all()
    for user in user_search:
        if not user.grandparent:
            user_search.remove(user)
    user_grandparents = current_user.all_grandparents
    return render_template('twitter/manage.html', user_search=user_search, user_grandparents=user_grandparents, form=form)

@app.route('/register/add/<id>')
def add(id):
    new_grandparent = User.query.filter_by(id=id).first()
    current_user.all_grandparents.append(new_grandparent)
    db.session.commit()
    return redirect(url_for('manage'))

@app.route('/register/grandchild', methods=('GET', 'POST'))
def register_grandchild():
    form = Grandchild_Registration(request.form)
    #if request.method == 'POST' and form.validate():
    if request.method == 'POST' and form.validate():
        print('validated')
        user = User()
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.username = form.username.data
        user.password = form.password.data
        user.grandparent = False

        print('first name: ', user.first_name)
        print('last name: ', user.last_name)
        print('username: ', user.username)
        
        print('doing profile pic')
        # profile pic
        user.profile_picture = form.profile.data

        # photo = photo_form.profile_picture.data
        # print('photo: ', photo)
        # filename = str(user.username) + '_profile'
        # print('filename: ', filename)
        # target = os.path.join(APP_ROOT, 'static/profile_pics')
        # print('target: ', target)
        # if not os.path.isdir(target):
        #     os.mkdir(target)
        # destination = "/".join([target, filename])
        # print('destination: ', destination)
        # photo.save(destination)
        # user.profile_picture = filename

        # language prefs
        user.display_language = form.display_language.data
        user.spoken_language = form.spoken_language.data

        # add user to database
        db.session.add(user)
        db.session.commit()
        flash('Thanks for registering!')
        login_user(user)
        return redirect(url_for('manage'))
    return render_template('twitter/register.html', form=form, gp_registration=False)

@app.route('/register/grandparent_info')
def grandparent_info():
    return render_template('twitter/grandparent_info.html')

@app.route('/login/<grandparent>', methods=('GET', 'POST'))
def login(grandparent):
    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        # information user has entered
        entered_username = form.username.data
        entered_password = form.password.data
        flash('done with username and password')

        # ensures user exists & password correct, then returns user object
        error = None
        user = User.query.filter_by(username=entered_username).first()
        if user is None:
            error = 'Incorrect username.'
            flash(error)
        elif user.password != entered_password:
            error = 'Incorrect password.'
            flash(error)

        if error is None:
            login_user(user)
            flash('Logged in successfully.')
        
        return redirect(url_for('index'))
    return render_template('twitter/login.html', form=form, is_grandparent=grandparent)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))

### IMAGE UPLOADS ###

def allowed_file(filename): 
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload():
    target = os.path.join(APP_ROOT, 'static/')
    print(target)

    if not os.path.isdir(target):
        os.mkdir(target)
    
    for file in request.files.getlist("file"):
        print(file)
        filename = file.filename
        destination = "/".join([target, filename])
        print(destination)
        file.save(destination)
        
        # save path to database
        author = User.query.filter_by(username=current_user.username).first()
        message = Message(body=filename, author=author)
        db.session.add(message)
        db.session.commit()
        return redirect(url_for('index'))

### CONTENT ###

@app.route('/')
def index():
    all_contacts = []
    if current_user.is_authenticated:
        all_contacts = []
        if current_user:
            if current_user.grandparent:
                all_contacts = current_user.all_grandchildren
            else:
                all_contacts = current_user.all_grandparents
        
        last_communication_list = []
        for contact in all_contacts:
            print(contact)
            if len(Message.query.filter_by(sender=current_user.id, recipient=contact.id).all()) > 0:
                last_communication = Message.query.filter_by(sender=current_user.id, recipient=contact.id).order_by(desc('timestamp')).first().timestamp
            else:
                last_communication = datetime.datetime.min
            last_communication_list.append((last_communication, contact))
        
        print('last communication: ', last_communication_list)
        last_communication_list.sort(key=lambda x: x[0], reverse=True)

        all_contacts = []

        for contact_tuple in last_communication_list:
            all_contacts.append(contact_tuple[1])
    else:
        redirect(url_for('landing'))
    return render_template('twitter/all_messages.html', contacts=all_contacts)

@app.route('/user_details/<recip_id>')
def user_details(recip_id):
    recipient = User.query.filter_by(id=recip_id).first()
    all_messages = []
    # messages from current user
    from_current = Message.query.filter_by(sender=current_user.id, recipient=recipient.id).all()
    # messages to current user
    to_current = Message.query.filter_by(sender=recipient.id, recipient=current_user.id).all()
    # combine and sort by timestamp
    all_messages = from_current + to_current
    all_messages.sort(key=lambda x: x.timestamp)

    all_contacts = []
    if current_user:
        if current_user.grandparent:
            all_contacts = current_user.all_grandchildren
        else:
            all_contacts = current_user.all_grandparents
    
    last_communication_list = []
    for contact in all_contacts:
        print(contact)
        if len(Message.query.filter_by(sender=current_user.id, recipient=contact.id).all()) > 0:
            last_communication = Message.query.filter_by(sender=current_user.id, recipient=contact.id).order_by(desc('timestamp')).first().timestamp
        else:
            last_communication = datetime.datetime.min
        last_communication_list.append((last_communication, contact))
    
    print('last communication: ', last_communication_list)
    last_communication_list.sort(key=lambda x: x[0], reverse=True)

    all_contacts = []

    for contact_tuple in last_communication_list:
        all_contacts.append(contact_tuple[1])


    return render_template('twitter/user_details.html', messages=all_messages, recipient=recipient, contacts=all_contacts)

@app.route('/grandparents')
def grandparents():
    return render_template('twitter/grandparents.html', grandparents=User.query.filter_by(grandparent=1).all())

@app.route('/grandchildren')
def grandchildren():
    return render_template('twitter/grandchildren.html', grandchildren=User.query.filter_by(grandparent=0).all())

# translation
def translate_text(text, source='en', target='en'):
    translate_client = translate.Client()
    result = translate_client.translate(text, source_language=source, target_language=target)
    print("Text: ", result['input'])
    print('Translation: ', result['translatedText'])
    return result['translatedText']