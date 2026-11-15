import flask
import flask_login
import auth
import discovery
import interests
import profiles
import find_new_interest
import user_account
from models import (
	Category,
	ChatRoom,
	Connection,
	Interest,
	RoomMessage,
	User,
	UserInterest,
	db,
)

app = flask.Flask(__name__)
app.config["SECRET_KEY"] = "change-this-hackathon-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


login_manager = flask_login.LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def user_loader(user_id):
	return db.session.get(User, user_id)


@login_manager.unauthorized_handler
def unauthorized():
	return flask.render_template("unauthorized.html")


with app.app_context():
	db.create_all()

# Interest discovery, tags and interest pages (see interests.py)
interests.init_app(app)

# Profile pages at /u/<handle> (see profiles.py; mock data in profile_api.py)
profiles.init_app(app)


@app.get("/account")
@flask_login.login_required
def account():
	return flask.render_template("account.html")


# LOGIN #

@app.get("/login")
def login_get():
	return flask.render_template("login.html")


@app.post("/login")
def login_post():
	identifier = flask.request.form.get("identifier", "").strip()
	password = flask.request.form.get("password", "")

	# Matches either username (CIS code) or email in the database
	user = auth.verify_user(username=identifier,
                         email=identifier, password=password)
	if not user:
		return flask.redirect(flask.url_for("login_get"))

	flask_login.login_user(user)
	return flask.redirect(flask.url_for("home"))


@app.route("/logout")
def logout():
	flask_login.logout_user()
	return flask.redirect(flask.url_for("login_get"))


@app.route("/register", methods=["GET", "POST"])
def register():
	if flask.request.method == "POST":
		username = flask.request.form.get("username", "").strip()
		email = flask.request.form.get("email", "").strip()
		password = flask.request.form.get("password", "")
		confirm_password = flask.request.form.get("confirm_password", "")

		# Make sure required fields are filled and not already taken
		if not username or not email or not password:
			return flask.render_template("register.html")

		if password != confirm_password:
			return flask.render_template("register.html")

		# Durham students only: a student-style @durham.ac.uk address. Staff addresses
		# are firstname.lastname@, so a dot before the @ is refused. This restricts
		# sign-up only; it does NOT prove the person owns the inbox.
		local, _, domain = email.lower().rpartition("@")
		if domain != "durham.ac.uk" or not local or "." in local:
			return flask.render_template(
				"register.html",
				error="Please use your student @durham.ac.uk address.",
			)

		if auth.is_user(email, username):
			return flask.render_template("register.html")

		auth.register_user(
			username=username,
			email=email,
			password=password,

		)
		user = auth.load_user(username=username, email=email)
		flask_login.login_user(user)
		return flask.render_template("success.html")

	return flask.render_template("register.html")


with app.app_context():
	db.create_all()


@app.post("/update-account")
@flask_login.login_required
def update_account():
    user_account.update_user_account(
        user=flask_login.current_user,
        new_username=flask.request.form.get("new-username", ""),
        new_bio=flask.request.form.get("new-bio", ""),
        new_interests=flask.request.form.get("new-interests", ""),
        remove_interests=flask.request.form.get("remove-interests", ""),
    )
    return flask.redirect(flask.url_for("account"))


@app.get("/find-new-interest")
@flask_login.login_required
def discover_new_interest():
    recommended = find_new_interest.find_new_interest(flask_login.current_user)
    if recommended:
        return flask.redirect(
            flask.url_for("interests.view_interest",
                          interest_id=recommended.interest_id)
        )
    return flask.redirect(flask.url_for("account"))


@app.route("/")
def home():
	return flask.render_template("index.html", chips=discovery.suggested_names(16))


if __name__ == "__main__":
	app.run("127.0.0.1", 5000)
