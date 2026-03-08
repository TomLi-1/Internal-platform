import logging
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from functools import wraps
from types import SimpleNamespace

import jwt
from flask import (
    Flask,
    current_app,
    jsonify,
    render_template,
    request,
    g,
    redirect,
    send_file,
    url_for,
)
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import selectinload

from config import get_database_url
from fake_data import (
    format_display_time,
    generate_posts,
    generate_stories,
    generate_suggestions,
    generate_user,
)
from models import Comment, Following, LikeComment, LikePost, Post, Story, User, db


def _configure_logging(app):
    if app.logger.handlers:
        return
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def _to_obj(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_obj(val) for key, val in value.items()})
    if isinstance(value, list):
        return [_to_obj(val) for val in value]
    return value


def _load_fake_feed():
    profile = _to_obj(generate_user())
    suggestions = _to_obj(generate_suggestions())
    stories = _to_obj(generate_stories())
    posts = _to_obj(generate_posts(n=6, width=600, height=430))
    for post in posts:
        if getattr(post, "caption", None) is None and getattr(post, "title", None):
            post.caption = post.title
        post.like_count = post.likes
    return profile, suggestions, stories, posts


def _load_db_feed():
    profile = User.query.order_by(User.id).first()
    if not profile:
        return None

    suggestions = (
        User.query.filter(User.id != profile.id).order_by(User.id).limit(5).all()
    )
    stories = (
        Story.query.options(selectinload(Story.user))
        .order_by(Story.pub_date.desc())
        .limit(10)
        .all()
    )
    posts = (
        Post.query.options(
            selectinload(Post.user),
            selectinload(Post.comments).selectinload(Comment.user),
            selectinload(Post.likes),
        )
        .order_by(Post.pub_date.desc())
        .limit(10)
        .all()
    )
    for post in posts:
        post.like_count = len(post.likes)
        post.display_time = format_display_time(post.pub_date)
    return profile, suggestions, stories, posts


def _serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "image_url": user.image_url,
        "thumb_url": user.thumb_url,
    }


def _serialize_comment(comment):
    return {
        "id": comment.id,
        "text": comment.text,
        "user": _serialize_user(comment.user),
        "post_id": comment.post_id,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


def _serialize_post(post, include_comments=False):
    data = {
        "id": post.id,
        "image_url": post.image_url,
        "caption": post.caption,
        "user": _serialize_user(post.user),
        "like_count": len(post.likes),
        "comment_count": len(post.comments),
        "pub_date": post.pub_date.isoformat() if post.pub_date else None,
    }
    if include_comments:
        data["comments"] = [_serialize_comment(comment) for comment in post.comments]
    return data


def _json_error(message, status_code):
    return jsonify({"error": message}), status_code


def _create_token(user_id):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(
        hours=int(current_app.config.get("JWT_EXPIRES_HOURS", 6))
    )
    payload = {
        # JWT "sub" should be a string per spec (and PyJWT enforces this in newer versions).
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token


def _decode_token(token):
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET_KEY"],
        algorithms=["HS256"],
    )


def _user_id_from_payload(payload):
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None


def _get_token_from_request():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header.split(" ", 1)[1].strip()
        if token:
            return token
    return request.cookies.get("auth_token")


def _current_user_from_token():
    token = _get_token_from_request()
    if not token:
        return None
    try:
        payload = _decode_token(token)
    except jwt.InvalidTokenError:
        return None
    user_id = _user_id_from_payload(payload)
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def _set_auth_cookie(response, token):
    max_age = int(current_app.config.get("JWT_EXPIRES_HOURS", 6)) * 3600
    response.set_cookie(
        "auth_token",
        token,
        httponly=True,
        samesite="Lax",
        secure=bool(current_app.config.get("AUTH_COOKIE_SECURE")),
        max_age=max_age,
    )


def _clear_auth_cookie(response):
    response.delete_cookie("auth_token", path="/")


def _issue_auth_response(user, status_code=200):
    token = _create_token(user.id)
    response = jsonify({"token": token, "user": _serialize_user(user)})
    _set_auth_cookie(response, token)
    return response, status_code


def _fill_feed_with_fake_data(profile, suggestions, stories, posts):
    fake_profile, fake_suggestions, fake_stories, fake_posts = _load_fake_feed()
    if not suggestions:
        suggestions = fake_suggestions
    if not stories:
        stories = fake_stories
    if not posts:
        posts = fake_posts
    return profile or fake_profile, suggestions, stories, posts


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_token_from_request()
        if not token:
            return _json_error("Authorization required.", 401)
        try:
            payload = _decode_token(token)
        except jwt.ExpiredSignatureError:
            return _json_error("Token expired.", 401)
        except jwt.InvalidTokenError:
            return _json_error("Invalid token.", 401)
        user_id = _user_id_from_payload(payload)
        if user_id is None:
            return _json_error("Invalid token.", 401)
        user = db.session.get(User, user_id)
        if not user:
            return _json_error("User not found.", 401)
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def create_app(config_overrides=None):
    app = Flask(__name__)

    config_overrides = config_overrides or {}
    database_url = config_overrides.get("SQLALCHEMY_DATABASE_URI") or get_database_url()
    if not database_url:
        raise RuntimeError("DB_URL or DATABASE_URL must be set to a Postgres URL.")

    app.config.update(
        {
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", "dev-secret"),
            "JWT_EXPIRES_HOURS": int(os.getenv("JWT_EXPIRES_HOURS", "6")),
            "AUTH_COOKIE_SECURE": os.getenv("AUTH_COOKIE_SECURE", "false").lower()
            == "true",
        }
    )
    app.config.update(config_overrides)

    db.init_app(app)
    _configure_logging(app)

    @app.after_request
    def log_api_response(response):
        if request.path.startswith("/api/"):
            app.logger.info("%s %s %s", request.method, request.path, response.status_code)
        return response

    @app.route("/openapi.json")
    def openapi_spec():
        return send_file(Path(__file__).with_name("openapi.json"))

    @app.route("/docs")
    def docs():
        return render_template("docs.html")

    @app.route("/login")
    def login_page():
        if _current_user_from_token():
            return redirect(url_for("index"))
        return render_template(
            "auth.html", mode="login", next_url=request.args.get("next") or ""
        )

    @app.route("/register")
    def register_page():
        if _current_user_from_token():
            return redirect(url_for("index"))
        return render_template(
            "auth.html", mode="register", next_url=request.args.get("next") or ""
        )

    @app.route("/auth/login", methods=["POST"])
    def login_form():
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            app.logger.info("Login failed: missing credentials.")
            return render_template(
                "auth.html",
                mode="login",
                next_url=request.args.get("next") or "",
                error="Username and password are required.",
            ), 400

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            app.logger.info("Login failed: invalid credentials for %s.", username)
            return render_template(
                "auth.html",
                mode="login",
                next_url=request.args.get("next") or "",
                error="Invalid credentials.",
            ), 401

        token = _create_token(user.id)
        next_url = request.form.get("next") or request.args.get("next") or url_for("index")
        response = redirect(next_url)
        _set_auth_cookie(response, token)
        app.logger.info("Login successful for %s.", username)
        return response

    @app.route("/auth/register", methods=["POST"])
    def register_form():
        data = {
            "username": request.form.get("username"),
            "email": request.form.get("email"),
            "first_name": request.form.get("first_name"),
            "last_name": request.form.get("last_name"),
            "password": request.form.get("password"),
        }
        missing = [field for field, value in data.items() if not value]
        if missing:
            app.logger.info("Register failed: missing fields %s.", ", ".join(missing))
            return render_template(
                "auth.html",
                mode="register",
                next_url=request.args.get("next") or "",
                error="Missing fields: " + ", ".join(missing),
            ), 400

        if User.query.filter_by(username=data["username"]).first():
            return render_template(
                "auth.html",
                mode="register",
                next_url=request.args.get("next") or "",
                error="Username already exists.",
            ), 409
        if User.query.filter_by(email=data["email"]).first():
            return render_template(
                "auth.html",
                mode="register",
                next_url=request.args.get("next") or "",
                error="Email already exists.",
            ), 409

        user = User(
            data["first_name"],
            data["last_name"],
            data["username"],
            data["email"],
        )
        user.set_password(data["password"])
        db.session.add(user)
        db.session.commit()

        token = _create_token(user.id)
        next_url = request.form.get("next") or request.args.get("next") or url_for("index")
        response = redirect(next_url)
        _set_auth_cookie(response, token)
        app.logger.info("Register successful for %s.", data["username"])
        return response

    @app.route("/logout")
    def logout():
        response = redirect(url_for("login_page"))
        _clear_auth_cookie(response)
        app.logger.info("User logged out.")
        return response

    @app.route("/")
    def index():
        current_user = _current_user_from_token()
        if not current_user:
            return redirect(url_for("login_page", next=request.path))
        try:
            data = _load_db_feed()
        except (OperationalError, ProgrammingError):
            data = None

        if not data:
            profile, suggestions, stories, posts = _load_fake_feed()
            profile = current_user
        else:
            profile, suggestions, stories, posts = data
            profile = current_user
            profile, suggestions, stories, posts = _fill_feed_with_fake_data(
                profile, suggestions, stories, posts
            )

        return render_template(
            "home.html",
            profile=profile,
            suggestions=suggestions,
            stories=stories,
            posts=posts,
            is_authenticated=True,
            current_user=current_user,
        )

    @app.route("/api/auth/register", methods=["POST"])
    def register():
        data = request.get_json(silent=True) or {}
        required = ["username", "email", "first_name", "last_name", "password"]
        missing = [field for field in required if not data.get(field)]
        if missing:
            app.logger.info("API register failed: missing fields %s.", ", ".join(missing))
            return _json_error("Missing fields: " + ", ".join(missing), 400)

        if User.query.filter_by(username=data["username"]).first():
            return _json_error("Username already exists.", 409)
        if User.query.filter_by(email=data["email"]).first():
            return _json_error("Email already exists.", 409)

        user = User(
            data["first_name"],
            data["last_name"],
            data["username"],
            data["email"],
        )
        user.set_password(data["password"])
        db.session.add(user)
        db.session.commit()

        app.logger.info("API register successful for %s.", data["username"])
        return _issue_auth_response(user, 201)

    @app.route("/api/auth/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or {}
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            app.logger.info("API login failed: missing credentials.")
            return _json_error("username and password are required.", 400)

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            app.logger.info("API login failed: invalid credentials for %s.", username)
            return _json_error("Invalid credentials.", 401)

        app.logger.info("API login successful for %s.", username)
        return _issue_auth_response(user)

    @app.route("/api/auth/me", methods=["GET"])
    @require_auth
    def auth_me():
        return jsonify(_serialize_user(g.current_user))

    @app.route("/api/posts", methods=["GET"])
    def list_posts():
        limit = request.args.get("limit", type=int)
        query = Post.query.options(
            selectinload(Post.user),
            selectinload(Post.comments).selectinload(Comment.user),
            selectinload(Post.likes),
        ).order_by(Post.pub_date.desc())
        if limit:
            query = query.limit(limit)
        posts = query.all()
        return jsonify({"posts": [_serialize_post(post) for post in posts]})

    @app.route("/api/posts/<int:post_id>", methods=["GET"])
    def get_post(post_id):
        post = (
            Post.query.options(
                selectinload(Post.user),
                selectinload(Post.comments).selectinload(Comment.user),
                selectinload(Post.likes),
            )
            .filter_by(id=post_id)
            .first()
        )
        if not post:
            return _json_error("Post not found.", 404)
        return jsonify(_serialize_post(post, include_comments=True))

    @app.route("/api/posts", methods=["POST"])
    @require_auth
    def create_post():
        data = request.get_json(silent=True) or {}
        image_url = data.get("image_url")
        caption = data.get("caption")
        if not image_url:
            return _json_error("image_url is required.", 400)
        post = Post(image_url, g.current_user.id, caption=caption)
        db.session.add(post)
        db.session.commit()
        post.user = g.current_user
        return jsonify(_serialize_post(post, include_comments=True)), 201

    @app.route("/api/posts/<int:post_id>", methods=["PUT"])
    @require_auth
    def update_post(post_id):
        post = (
            Post.query.options(
                selectinload(Post.user),
                selectinload(Post.comments).selectinload(Comment.user),
                selectinload(Post.likes),
            )
            .filter_by(id=post_id)
            .first()
        )
        if not post:
            return _json_error("Post not found.", 404)
        if post.user_id != g.current_user.id:
            return _json_error("Forbidden.", 403)

        data = request.get_json(silent=True) or {}
        if "caption" not in data and "image_url" not in data:
            return _json_error("Nothing to update.", 400)
        if "caption" in data:
            post.caption = data["caption"]
        if "image_url" in data:
            post.image_url = data["image_url"]
        db.session.commit()
        return jsonify(_serialize_post(post, include_comments=True))

    @app.route("/api/posts/<int:post_id>", methods=["DELETE"])
    @require_auth
    def delete_post(post_id):
        post = db.session.get(Post, post_id)
        if not post:
            return _json_error("Post not found.", 404)
        if post.user_id != g.current_user.id:
            return _json_error("Forbidden.", 403)
        db.session.delete(post)
        db.session.commit()
        return jsonify({"status": "deleted"})

    @app.route("/api/posts/<int:post_id>/comments", methods=["GET"])
    def list_comments(post_id):
        post = db.session.get(Post, post_id)
        if not post:
            return _json_error("Post not found.", 404)
        comments = (
            Comment.query.options(selectinload(Comment.user))
            .filter_by(post_id=post_id)
            .order_by(Comment.created_at.asc())
            .all()
        )
        return jsonify({"comments": [_serialize_comment(comment) for comment in comments]})

    @app.route("/api/posts/<int:post_id>/comments", methods=["POST"])
    @require_auth
    def create_comment(post_id):
        data = request.get_json(silent=True) or {}
        text = data.get("text")
        if not text:
            return _json_error("text is required.", 400)
        post = db.session.get(Post, post_id)
        if not post:
            return _json_error("Post not found.", 404)

        comment = Comment(text, g.current_user.id, post_id)
        db.session.add(comment)
        db.session.commit()
        comment.user = g.current_user
        return jsonify(_serialize_comment(comment)), 201

    @app.route("/api/comments/<int:comment_id>", methods=["GET"])
    def get_comment(comment_id):
        comment = (
            Comment.query.options(selectinload(Comment.user))
            .filter_by(id=comment_id)
            .first()
        )
        if not comment:
            return _json_error("Comment not found.", 404)
        return jsonify(_serialize_comment(comment))

    @app.route("/api/comments/<int:comment_id>", methods=["PUT"])
    @require_auth
    def update_comment(comment_id):
        comment = (
            Comment.query.options(selectinload(Comment.user))
            .filter_by(id=comment_id)
            .first()
        )
        if not comment:
            return _json_error("Comment not found.", 404)
        if comment.user_id != g.current_user.id:
            return _json_error("Forbidden.", 403)

        data = request.get_json(silent=True) or {}
        if "text" not in data:
            return _json_error("text is required.", 400)
        comment.text = data["text"]
        db.session.commit()
        return jsonify(_serialize_comment(comment))

    @app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
    @require_auth
    def delete_comment(comment_id):
        comment = db.session.get(Comment, comment_id)
        if not comment:
            return _json_error("Comment not found.", 404)
        if comment.user_id != g.current_user.id:
            return _json_error("Forbidden.", 403)
        db.session.delete(comment)
        db.session.commit()
        return jsonify({"status": "deleted"})

    @app.route("/api/posts/<int:post_id>/likes", methods=["POST"])
    @require_auth
    def like_post(post_id):
        post = db.session.get(Post, post_id)
        if not post:
            return _json_error("Post not found.", 404)
        like = LikePost(g.current_user.id, post_id)
        db.session.add(like)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"status": "already-liked"})
        return jsonify({"status": "liked"}), 201

    @app.route("/api/posts/<int:post_id>/likes", methods=["DELETE"])
    @require_auth
    def unlike_post(post_id):
        like = (
            LikePost.query.filter_by(user_id=g.current_user.id, post_id=post_id).first()
        )
        if not like:
            return _json_error("Like not found.", 404)
        db.session.delete(like)
        db.session.commit()
        return jsonify({"status": "unliked"})

    @app.route("/api/comments/<int:comment_id>/likes", methods=["POST"])
    @require_auth
    def like_comment(comment_id):
        comment = db.session.get(Comment, comment_id)
        if not comment:
            return _json_error("Comment not found.", 404)
        like = LikeComment(g.current_user.id, comment_id)
        db.session.add(like)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"status": "already-liked"})
        return jsonify({"status": "liked"}), 201

    @app.route("/api/comments/<int:comment_id>/likes", methods=["DELETE"])
    @require_auth
    def unlike_comment(comment_id):
        like = (
            LikeComment.query.filter_by(
                user_id=g.current_user.id, comment_id=comment_id
            ).first()
        )
        if not like:
            return _json_error("Like not found.", 404)
        db.session.delete(like)
        db.session.commit()
        return jsonify({"status": "unliked"})

    @app.route("/api/following", methods=["GET"])
    @require_auth
    def list_following():
        following = (
            User.query.join(Following, Following.following_id == User.id)
            .filter(Following.user_id == g.current_user.id)
            .order_by(User.username)
            .all()
        )
        return jsonify({"following": [_serialize_user(user) for user in following]})

    @app.route("/api/following/<int:user_id>", methods=["POST"])
    @require_auth
    def follow_user(user_id):
        if user_id == g.current_user.id:
            return _json_error("Cannot follow yourself.", 400)
        user = db.session.get(User, user_id)
        if not user:
            return _json_error("User not found.", 404)
        follow = Following(g.current_user.id, user_id)
        db.session.add(follow)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"status": "already-following"})
        return jsonify({"status": "following"}), 201

    @app.route("/api/following/<int:user_id>", methods=["DELETE"])
    @require_auth
    def unfollow_user(user_id):
        follow = (
            Following.query.filter_by(
                user_id=g.current_user.id, following_id=user_id
            ).first()
        )
        if not follow:
            return _json_error("Follow not found.", 404)
        db.session.delete(follow)
        db.session.commit()
        return jsonify({"status": "unfollowed"})

    return app


app = None
try:
    if get_database_url():
        app = create_app()
except RuntimeError:
    app = None


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True)
