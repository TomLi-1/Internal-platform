from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    image_url = db.Column(db.String(500))
    thumb_url = db.Column(db.String(500))
    password_hash = db.Column(db.String(255))
    password_plaintext = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship(
        "Post", back_populates="user", cascade="all, delete-orphan"
    )
    comments = db.relationship(
        "Comment", back_populates="user", cascade="all, delete-orphan"
    )
    stories = db.relationship(
        "Story", back_populates="user", cascade="all, delete-orphan"
    )

    def __init__(
        self, first_name, last_name, username, email, image_url=None, thumb_url=None
    ):
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.email = email
        self.image_url = image_url
        self.thumb_url = thumb_url

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash or "", password)


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    image_url = db.Column(db.String(500), nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    caption = db.Column(db.Text)
    pub_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", back_populates="posts")
    comments = db.relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    likes = db.relationship(
        "LikePost", back_populates="post", cascade="all, delete-orphan"
    )
    bookmarks = db.relationship(
        "Bookmark", back_populates="post", cascade="all, delete-orphan"
    )

    def __init__(self, image_url, user_id, caption=None, pub_date=None):
        self.image_url = image_url
        self.user_id = user_id
        self.caption = caption
        self.pub_date = pub_date or datetime.utcnow()


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    post_id = db.Column(
        db.Integer, db.ForeignKey("posts.id"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="comments")
    post = db.relationship("Post", back_populates="comments")
    likes = db.relationship(
        "LikeComment", back_populates="comment", cascade="all, delete-orphan"
    )

    def __init__(self, text, user_id, post_id):
        self.text = text
        self.user_id = user_id
        self.post_id = post_id


class Story(db.Model):
    __tablename__ = "stories"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    pub_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", back_populates="stories")

    def __init__(self, text, user_id, pub_date=None):
        self.text = text
        self.user_id = user_id
        self.pub_date = pub_date or datetime.utcnow()


class LikePost(db.Model):
    __tablename__ = "post_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    post_id = db.Column(
        db.Integer, db.ForeignKey("posts.id"), nullable=False, index=True
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "post_id", name="uq_post_like"),
    )

    user = db.relationship("User")
    post = db.relationship("Post", back_populates="likes")

    def __init__(self, user_id, post_id):
        self.user_id = user_id
        self.post_id = post_id


class LikeComment(db.Model):
    __tablename__ = "comment_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    comment_id = db.Column(
        db.Integer, db.ForeignKey("comments.id"), nullable=False, index=True
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "comment_id", name="uq_comment_like"),
    )

    user = db.relationship("User")
    comment = db.relationship("Comment", back_populates="likes")

    def __init__(self, user_id, comment_id):
        self.user_id = user_id
        self.comment_id = comment_id


class Bookmark(db.Model):
    __tablename__ = "bookmarks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    post_id = db.Column(
        db.Integer, db.ForeignKey("posts.id"), nullable=False, index=True
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "post_id", name="uq_bookmark"),
    )

    user = db.relationship("User")
    post = db.relationship("Post", back_populates="bookmarks")

    def __init__(self, user_id, post_id):
        self.user_id = user_id
        self.post_id = post_id


class Following(db.Model):
    __tablename__ = "following"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    following_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "following_id", name="uq_following"),
    )

    user = db.relationship("User", foreign_keys=[user_id])
    following = db.relationship("User", foreign_keys=[following_id])

    def __init__(self, user_id, following_id):
        self.user_id = user_id
        self.following_id = following_id
