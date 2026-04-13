
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def register_user(client, username, email, password="pass"):
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "first_name": username.capitalize(),
            "last_name": "User",
            "password": password,
        },
    )
    assert response.status_code == 201
    payload = response.get_json()
    return payload["user"]


def login_user(client, username, password="pass"):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    payload = response.get_json()
    return payload["token"], payload["user"]


def test_posts_comments_likes_follow(client):
    user1 = register_user(client, "alice", "alice@example.com")
    user2 = register_user(client, "bob", "bob@example.com")

    token1, _ = login_user(client, "alice")
    token2, _ = login_user(client, "bob")

    post_response = client.post(
        "/api/posts",
        json={"image_url": "https://picsum.photos/600/430", "caption": "hello"},
        headers=auth_headers(token1),
    )
    assert post_response.status_code == 201
    post = post_response.get_json()
    post_id = post["id"]

    forbidden = client.put(
        f"/api/posts/{post_id}",
        json={"caption": "nope"},
        headers=auth_headers(token2),
    )
    assert forbidden.status_code == 403

    updated = client.put(
        f"/api/posts/{post_id}",
        json={"caption": "updated"},
        headers=auth_headers(token1),
    )
    assert updated.status_code == 200

    comment_response = client.post(
        f"/api/posts/{post_id}/comments",
        json={"text": "nice"},
        headers=auth_headers(token2),
    )
    assert comment_response.status_code == 201
    comment = comment_response.get_json()
    comment_id = comment["id"]

    updated_comment = client.put(
        f"/api/comments/{comment_id}",
        json={"text": "very nice"},
        headers=auth_headers(token2),
    )
    assert updated_comment.status_code == 200
    assert updated_comment.get_json()["text"] == "very nice"

    like_response = client.post(
        f"/api/posts/{post_id}/likes",
        headers=auth_headers(token2),
    )
    assert like_response.status_code in (200, 201)

    unlike_response = client.delete(
        f"/api/posts/{post_id}/likes",
        headers=auth_headers(token2),
    )
    assert unlike_response.status_code == 200

    comment_like_response = client.post(
        f"/api/comments/{comment_id}/likes",
        headers=auth_headers(token1),
    )
    assert comment_like_response.status_code in (200, 201)

    comment_unlike_response = client.delete(
        f"/api/comments/{comment_id}/likes",
        headers=auth_headers(token1),
    )
    assert comment_unlike_response.status_code == 200

    follow_response = client.post(
        f"/api/following/{user2['id']}",
        headers=auth_headers(token1),
    )
    assert follow_response.status_code in (200, 201)

    list_following = client.get("/api/following", headers=auth_headers(token1))
    assert list_following.status_code == 200
    data = list_following.get_json()
    assert any(user["id"] == user2["id"] for user in data["following"])

    unfollow_response = client.delete(
        f"/api/following/{user2['id']}",
        headers=auth_headers(token1),
    )
    assert unfollow_response.status_code == 200

    delete_comment_response = client.delete(
        f"/api/comments/{comment_id}",
        headers=auth_headers(token2),
    )
    assert delete_comment_response.status_code == 200
