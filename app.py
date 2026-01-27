from types import SimpleNamespace

from flask import Flask, jsonify, render_template, request
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
def create_post():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    image_url = data.get("image_url")
    caption = data.get("caption")
    if not user_id or not image_url:
        return _json_error("user_id and image_url are required.", 400)
    user = db.session.get(User, user_id)
    if not user:
        return _json_error("User not found.", 404)
    post = Post(image_url, user_id, caption=caption)
    db.session.add(post)
    db.session.commit()
    post.user = user
    return jsonify(_serialize_post(post, include_comments=True)), 201


@app.route("/api/posts/<int:post_id>", methods=["PUT"])
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
def delete_post(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        return _json_error("Post not found.", 404)
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
def create_comment(post_id):
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    text = data.get("text")
    if not user_id or not text:
        return _json_error("user_id and text are required.", 400)
    post = db.session.get(Post, post_id)
    if not post:
        return _json_error("Post not found.", 404)
    user = db.session.get(User, user_id)
    if not user:
        return _json_error("User not found.", 404)
    comment = Comment(text, user_id, post_id)
    db.session.add(comment)
    db.session.commit()
    comment.user = user
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
def update_comment(comment_id):
    comment = (
        Comment.query.options(selectinload(Comment.user))
        .filter_by(id=comment_id)
        .first()
    )
    if not comment:
        return _json_error("Comment not found.", 404)
    data = request.get_json(silent=True) or {}
    if "text" not in data:
        return _json_error("text is required.", 400)
    comment.text = data["text"]
    db.session.commit()
    return jsonify(_serialize_comment(comment))


@app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
def delete_comment(comment_id):
    comment = db.session.get(Comment, comment_id)
    if not comment:
        return _json_error("Comment not found.", 404)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({"status": "deleted"})


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
