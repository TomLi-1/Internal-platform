from types import SimpleNamespace

from flask import Flask, render_template
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import selectinload

from config import get_database_url
from fake_data import (
    format_display_time,
    generate_posts,
    generate_stories,
    generate_suggestions,
    generate_user,
)
from models import Comment, Post, Story, User, db

app = Flask(__name__)

database_url = get_database_url()
if not database_url:
    raise RuntimeError("DB_URL or DATABASE_URL must be set to a Postgres URL.")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


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


@app.route("/")
def index():
    try:
        data = _load_db_feed()
    except (OperationalError, ProgrammingError):
        data = None

    if not data:
        profile, suggestions, stories, posts = _load_fake_feed()
    else:
        profile, suggestions, stories, posts = data

    return render_template(
        "home.html",
        profile=profile,
        suggestions=suggestions,
        stories=stories,
        posts=posts,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
