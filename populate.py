import random
from datetime import datetime, timedelta

from faker import Faker
from flask import Flask

from config import get_database_url
from fake_data import generate_image
from models import (
    Bookmark,
    Comment,
    Following,
    LikeComment,
    LikePost,
    Post,
    Story,
    User,
    db,
)

fake = Faker()

app = Flask(__name__)

database_url = get_database_url()
if not database_url:
    raise RuntimeError("DB_URL or DATABASE_URL must be set to seed the database.")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

users = []
posts = []
comments = []
ppl_user_is_following_map = {}


def _reset_tracking():
    users.clear()
    posts.clear()
    comments.clear()
    ppl_user_is_following_map.clear()


def _create_user():
    profile = fake.simple_profile()
    tokens = profile["name"].split(" ")
    first_name = tokens.pop(0)
    last_name = " ".join(tokens)
    username = "{0}_{1}".format(first_name, last_name.replace(" ", "_")).lower()
    provider = profile["mail"].split("@")[1]
    email = "{0}@{1}".format(username, provider)

    user = User(
        first_name,
        last_name,
        username,
        email,
        image_url=generate_image(),
        thumb_url=generate_image(width=30, height=30),
    )
    password = (
        fake.sentence(nb_words=3).replace(" ", "_").replace(".", "").lower()
    )
    user.password_plaintext = password
    user.set_password(fake.password(15, 25))
    return user


def _create_post(user):
    time_of_post = datetime.now() - timedelta(hours=random.randint(1, 100))
    return Post(
        generate_image(width=600, height=430),
        user.id,
        caption=fake.sentence(nb_words=random.randint(15, 50)),
        pub_date=time_of_post,
    )


def _create_story(user):
    time_of_post = datetime.now() - timedelta(hours=random.randint(1, 100))
    return Story(
        fake.sentence(nb_words=random.randint(10, 30)),
        user.id,
        pub_date=time_of_post,
    )


def _create_post_likes(post, follower_ids):
    user_ids = follower_ids.copy()
    if not user_ids:
        return
    for _ in range(random.randint(0, 5)):
        i = random.randint(0, len(user_ids) - 1)
        user_id = user_ids.pop(i)
        db.session.add(LikePost(user_id, post.id))
        if len(user_ids) == 0:
            break


def _create_post_bookmarks(post, follower_ids):
    user_ids = follower_ids.copy()
    if not user_ids:
        return
    for _ in range(random.randint(0, 4)):
        i = random.randint(0, len(user_ids) - 1)
        user_id = user_ids.pop(i)
        db.session.add(Bookmark(user_id, post.id))
        if len(user_ids) == 0:
            break


def _create_comment(post, follower_ids):
    return Comment(
        fake.sentence(nb_words=random.randint(15, 50)),
        random.choice(follower_ids),
        post.id,
    )


def create_users(n=30):
    created = []
    for _ in range(n):
        user = _create_user()
        users.append(user)
        created.append(user)
        db.session.add(user)
    db.session.commit()
    return created


def create_accounts_that_you_follow(seed_users):
    for user in seed_users:
        accounts_to_follow = []
        while len(accounts_to_follow) < min(10, max(0, len(seed_users) - 1)):
            candidate_account = random.choice(seed_users)
            if candidate_account != user and candidate_account not in accounts_to_follow:
                db.session.add(Following(user.id, candidate_account.id))

                if user.id not in ppl_user_is_following_map:
                    ppl_user_is_following_map[user.id] = []
                ppl_user_is_following_map[user.id].append(candidate_account.id)

                accounts_to_follow.append(candidate_account)
    db.session.commit()


def create_posts(seed_users):
    created = []
    for user in seed_users:
        for _ in range(random.randint(6, 12)):
            post = _create_post(user)
            posts.append(post)
            created.append(post)
            db.session.add(post)
    db.session.commit()
    return created


def create_stories(seed_users):
    for i, user in enumerate(seed_users):
        if i % 3:
            db.session.add(_create_story(user))
    db.session.commit()


def _get_people_who_follow(user_id):
    user_ids_tuples = (
        db.session.query(Following.user_id)
        .filter(Following.following_id == user_id)
        .order_by(Following.user_id)
        .all()
    )
    return [id for (id,) in user_ids_tuples]


def create_post_likes(seed_posts):
    for post in seed_posts:
        auth_user_ids = _get_people_who_follow(post.user_id)
        _create_post_likes(post, auth_user_ids)
    db.session.commit()


def create_bookmarks(seed_posts):
    for post in seed_posts:
        auth_user_ids = _get_people_who_follow(post.user_id)
        _create_post_bookmarks(post, auth_user_ids)
    db.session.commit()


def create_comments(seed_posts):
    created = []
    for post in seed_posts:
        auth_user_ids = _get_people_who_follow(post.user_id)
        if not auth_user_ids:
            continue
        for _ in range(random.randint(0, 5)):
            comment = _create_comment(post, auth_user_ids)
            db.session.add(comment)
            comments.append(comment)
            created.append(comment)
    db.session.commit()
    return created


def create_comment_likes(seed_comments):
    for comment in seed_comments:
        auth_user_ids = _get_people_who_follow(comment.user_id)
        if not auth_user_ids:
            continue
        for _ in range(random.randint(0, 3)):
            i = random.randint(0, len(auth_user_ids) - 1)
            user_id = auth_user_ids.pop(i)
            db.session.add(LikeComment(user_id, comment.id))
            if len(auth_user_ids) == 0:
                break
    db.session.commit()


def seed_database(reset=False, min_users=12, min_posts=24):
    with app.app_context():
        _reset_tracking()

        if reset:
            db.drop_all()

        db.create_all()

        existing_users = User.query.count()
        existing_posts = Post.query.count()

        if not reset and existing_users >= min_users and existing_posts >= min_posts:
            print("Sample data already present. Skipping seed.")
            return

        users_needed = max(0, min_users - existing_users)
        if users_needed == 0 and existing_posts >= min_posts:
            print("Database already has enough users and posts. Skipping seed.")
            return

        print("Seeding sample data...")
        seed_users = create_users(n=max(users_needed, 12 if reset else users_needed))
        if not seed_users:
            print("No new users needed; skipping seed user generation.")
            return

        create_accounts_that_you_follow(seed_users)
        seed_posts = create_posts(seed_users)
        create_stories(seed_users)
        create_post_likes(seed_posts)
        create_bookmarks(seed_posts)
        seed_comments = create_comments(seed_posts)
        create_comment_likes(seed_comments)
        print("Sample data ready.")


if __name__ == "__main__":
    seed_database(reset=True, min_users=30, min_posts=180)
