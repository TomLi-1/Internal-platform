function initFeedActions() {
  const body = document.body;
  let currentUserId = String(body.dataset.currentUserId || "");
  let currentUsername = body.dataset.currentUsername || "you";
  let currentUser = null;

  const cardPanel = document.querySelector(".cardPanel");
  const suggestionPanel = document.querySelector(".suggestions");
  const createPostForm = document.getElementById("createPostForm");
  const createPostStatus = document.getElementById("createPostStatus");

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function apiJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
    });
    const text = await response.text();
    let payload = {};

    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        payload = { error: text };
      }
    }

    if (!response.ok) {
      throw new Error(payload.error || "Request failed.");
    }

    return payload;
  }

  async function ensureSession() {
    if (currentUser) {
      return currentUser;
    }

    try {
      const payload = await apiJson("/api/auth/me");
      currentUser = payload;
      currentUserId = String(payload.id || currentUserId || "");
      currentUsername = payload.username || currentUsername;
      return currentUser;
    } catch (error) {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search
      );
      window.location.href = `/login?next=${next}`;
      return null;
    }
  }

  function updateFollowButton(button, isFollowing) {
    button.dataset.following = isFollowing ? "true" : "false";
    button.textContent = isFollowing ? "Following" : "Follow";
    button.classList.toggle("isFollowing", isFollowing);
  }

  function updatePostLikeButton(button, liked) {
    button.dataset.liked = liked ? "true" : "false";
    button.textContent = liked ? "Unlike" : "Like";
    button.classList.toggle("isActive", liked);
  }

  function updateCommentLikeButton(button, liked) {
    button.dataset.liked = liked ? "true" : "false";
    button.textContent = liked ? "Unlike" : "Like";
    button.classList.toggle("isActive", liked);
  }

  function createCommentElement(comment) {
    const wrapper = document.createElement("div");
    wrapper.className = "comment";
    wrapper.dataset.commentId = String(comment.id || "");
    wrapper.dataset.ownerId = String(comment.user && comment.user.id ? comment.user.id : "");

    wrapper.innerHTML = `
      <p class="postUser"><strong>${escapeHtml(
        comment.user && comment.user.username ? comment.user.username : "user"
      )}</strong></p>
      <p class="commentText">${escapeHtml(comment.text || "")}</p>
      <button
        class="commentLikeButton${comment.viewer_has_liked ? " isActive" : ""}"
        data-comment-id="${escapeHtml(comment.id || "")}"
        data-liked="${comment.viewer_has_liked ? "true" : "false"}"
        type="button"
      >
        ${comment.viewer_has_liked ? "Unlike" : "Like"}
      </button>
      <span class="commentLikeCount">${Number(comment.like_count || 0)}</span>
      ${
        comment.is_owner
          ? `<button class="editCommentButton" data-comment-id="${escapeHtml(
              comment.id || ""
            )}" type="button">Edit</button>
             <button class="deleteCommentButton" data-comment-id="${escapeHtml(
               comment.id || ""
             )}" type="button">Delete</button>`
          : ""
      }
    `;

    return wrapper;
  }

  function renderPostCard(post) {
    const postId = String(post.id || "");
    const isOwner = Boolean(post.is_owner);
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.postId = postId;
    card.dataset.ownerId = String(post.user && post.user.id ? post.user.id : "");

    card.innerHTML = `
      <div class="postHeader">
        <div class="postUser">${escapeHtml(
          post.user && post.user.username ? post.user.username : currentUsername
        )}</div>
        <div class="postActions">
          ${
            isOwner
              ? `<button class="editPostButton" data-post-id="${escapeHtml(
                  postId
                )}" type="button">Edit</button>
                 <button class="deletePostButton" data-post-id="${escapeHtml(
                   postId
                 )}" type="button">Delete</button>`
              : '<em class="fas fa-ellipsis-h"></em>'
          }
        </div>
      </div>
      <div class="postPic">
        <img class="postImage" src="${escapeHtml(post.image_url || "")}" alt="postPic"/>
      </div>
      <div class="postContent">
        <div class="icons">
          <div class="threeIcons">
            <button
              class="iconButton postLikeButton${post.viewer_has_liked ? " isActive" : ""}"
              data-post-id="${escapeHtml(postId)}"
              data-liked="${post.viewer_has_liked ? "true" : "false"}"
              type="button"
            >
              ${post.viewer_has_liked ? "Unlike" : "Like"}
            </button>
            <em class="far fa-comment"></em>
            <em class="far fa-paper-plane"></em>
          </div>
          <div>
            <em class="far fa-bookmark"></em>
          </div>
        </div>
        <p class="postLikes"><strong><span class="postLikeCount">${Number(
          post.like_count || 0
        )}</span> Likes</strong></p>
        <div class="realContent">
          <p class="postUser"><strong>${escapeHtml(
            post.user && post.user.username ? post.user.username : currentUsername
          )}</strong></p>
          <p class="postCaption">${escapeHtml(post.caption || "")}</p>
        </div>
        <div class="comments">
          <div class="postTime" style="color: darkgrey;font: 0.9em sans-serif;">Just now</div>
        </div>
        <div class="addCommentSection">
          <div class="addComment">
            <em class="far fa-smile"></em>
            <input placeholder="Add a comment"/>
          </div>
          <button class="postCommentButton" type="button">Post</button>
        </div>
      </div>
    `;

    const commentsContainer = card.querySelector(".comments");
    const timeEl = commentsContainer.querySelector(".postTime");
    (post.comments || []).slice(0, 2).forEach((comment) => {
      commentsContainer.insertBefore(createCommentElement(comment), timeEl);
    });

    return card;
  }

  async function handleCreatePost(event) {
    event.preventDefault();

    const session = await ensureSession();
    if (!session) {
      return;
    }

    const imageInput = createPostForm.querySelector("#postImageUrl");
    const captionInput = createPostForm.querySelector("#postCaption");
    const submitButton = createPostForm.querySelector("button[type='submit']");
    const imageUrl = imageInput.value.trim();
    const caption = captionInput.value.trim();

    if (!imageUrl) {
      createPostStatus.textContent = "Image URL is required.";
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Posting...";
    createPostStatus.textContent = "";

    try {
      const post = await apiJson("/api/posts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_url: imageUrl, caption }),
      });
      cardPanel.prepend(renderPostCard(post));
      createPostForm.reset();
      createPostStatus.textContent = "Post created.";
    } catch (error) {
      createPostStatus.textContent = error.message;
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Post";
    }
  }

  async function handleEditPost(button) {
    const card = button.closest(".card");
    if (!card) {
      return;
    }

    const postId = card.dataset.postId;
    const captionEl = card.querySelector(".postCaption");
    const imageEl = card.querySelector(".postImage");
    const currentCaption = captionEl ? captionEl.textContent || "" : "";
    const currentImageUrl = imageEl ? imageEl.getAttribute("src") || "" : "";

    const nextCaption = window.prompt("Edit caption:", currentCaption);
    if (nextCaption === null) {
      return;
    }

    const nextImageUrl = window.prompt("Edit image URL:", currentImageUrl);
    if (nextImageUrl === null) {
      return;
    }

    const payload = {};
    if (nextCaption !== currentCaption) {
      payload.caption = nextCaption;
    }
    if (nextImageUrl !== currentImageUrl) {
      payload.image_url = nextImageUrl;
    }

    if (Object.keys(payload).length === 0) {
      return;
    }

    button.disabled = true;
    button.textContent = "Saving...";

    try {
      const updated = await apiJson(`/api/posts/${postId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (captionEl) {
        captionEl.textContent = updated.caption || "";
      }
      if (imageEl) {
        imageEl.setAttribute("src", updated.image_url || "");
      }
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Edit";
    }
  }

  async function handleDeletePost(button) {
    const card = button.closest(".card");
    const postId = card ? card.dataset.postId : "";
    if (!postId || !window.confirm("Delete this post?")) {
      return;
    }

    button.disabled = true;
    button.textContent = "Deleting...";

    try {
      await apiJson(`/api/posts/${postId}`, { method: "DELETE" });
      if (card) {
        card.remove();
      }
    } catch (error) {
      window.alert(error.message);
      button.disabled = false;
      button.textContent = "Delete";
    }
  }

  async function handleTogglePostLike(button) {
    const card = button.closest(".card");
    const postId = card ? card.dataset.postId : "";
    if (!postId) {
      return;
    }

    const currentlyLiked = button.dataset.liked === "true";
    const countEl = card.querySelector(".postLikeCount");
    const currentCount = Number(countEl ? countEl.textContent : 0);

    button.disabled = true;

    try {
      await apiJson(`/api/posts/${postId}/likes`, {
        method: currentlyLiked ? "DELETE" : "POST",
      });
      updatePostLikeButton(button, !currentlyLiked);
      if (countEl) {
        countEl.textContent = String(
          Math.max(0, currentCount + (currentlyLiked ? -1 : 1))
        );
      }
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function handleCreateComment(button) {
    const card = button.closest(".card");
    if (!card) {
      return;
    }

    const postId = card.dataset.postId;
    const input = card.querySelector(".addCommentSection input");
    const text = input ? input.value.trim() : "";

    if (!postId) {
      return;
    }
    if (!text) {
      window.alert("Write a comment first.");
      return;
    }

    button.disabled = true;
    button.textContent = "Posting...";

    try {
      const comment = await apiJson(`/api/posts/${postId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const commentsContainer = card.querySelector(".comments");
      const timeEl = commentsContainer.querySelector(".postTime");
      commentsContainer.insertBefore(createCommentElement(comment), timeEl);
      if (input) {
        input.value = "";
      }
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Post";
    }
  }

  async function handleEditComment(button) {
    const commentEl = button.closest(".comment");
    if (!commentEl) {
      return;
    }

    const commentId = commentEl.dataset.commentId;
    const textEl = commentEl.querySelector(".commentText");
    const currentText = textEl ? textEl.textContent || "" : "";
    const nextText = window.prompt("Edit comment:", currentText);

    if (nextText === null || nextText === currentText) {
      return;
    }

    button.disabled = true;
    button.textContent = "Saving...";

    try {
      const updated = await apiJson(`/api/comments/${commentId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: nextText }),
      });
      if (textEl) {
        textEl.textContent = updated.text || "";
      }
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Edit";
    }
  }

  async function handleDeleteComment(button) {
    const commentEl = button.closest(".comment");
    const commentId = commentEl ? commentEl.dataset.commentId : "";
    if (!commentId || !window.confirm("Delete this comment?")) {
      return;
    }

    button.disabled = true;
    button.textContent = "Deleting...";

    try {
      await apiJson(`/api/comments/${commentId}`, { method: "DELETE" });
      if (commentEl) {
        commentEl.remove();
      }
    } catch (error) {
      window.alert(error.message);
      button.disabled = false;
      button.textContent = "Delete";
    }
  }

  async function handleToggleCommentLike(button) {
    const commentEl = button.closest(".comment");
    const commentId = commentEl ? commentEl.dataset.commentId : "";
    if (!commentId) {
      return;
    }

    const currentlyLiked = button.dataset.liked === "true";
    const countEl = commentEl.querySelector(".commentLikeCount");
    const currentCount = Number(countEl ? countEl.textContent : 0);

    button.disabled = true;

    try {
      await apiJson(`/api/comments/${commentId}/likes`, {
        method: currentlyLiked ? "DELETE" : "POST",
      });
      updateCommentLikeButton(button, !currentlyLiked);
      if (countEl) {
        countEl.textContent = String(
          Math.max(0, currentCount + (currentlyLiked ? -1 : 1))
        );
      }
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function handleToggleFollow(button) {
    const userId = button.dataset.userId;
    if (!userId) {
      return;
    }

    const currentlyFollowing = button.dataset.following === "true";
    button.disabled = true;

    try {
      await apiJson(`/api/following/${userId}`, {
        method: currentlyFollowing ? "DELETE" : "POST",
      });
      updateFollowButton(button, !currentlyFollowing);
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
    }
  }

  if (createPostForm) {
    createPostForm.addEventListener("submit", handleCreatePost);
  }

  if (suggestionPanel) {
    suggestionPanel.addEventListener("click", (event) => {
      const followButton = event.target.closest(".followToggleButton");
      if (followButton) {
        event.preventDefault();
        handleToggleFollow(followButton);
      }
    });
  }

  if (cardPanel) {
    cardPanel.addEventListener("click", (event) => {
      const postLikeButton = event.target.closest(".postLikeButton");
      if (postLikeButton) {
        event.preventDefault();
        handleTogglePostLike(postLikeButton);
        return;
      }

      const commentButton = event.target.closest(".postCommentButton");
      if (commentButton) {
        event.preventDefault();
        handleCreateComment(commentButton);
        return;
      }

      const editPostButton = event.target.closest(".editPostButton");
      if (editPostButton) {
        event.preventDefault();
        handleEditPost(editPostButton);
        return;
      }

      const deletePostButton = event.target.closest(".deletePostButton");
      if (deletePostButton) {
        event.preventDefault();
        handleDeletePost(deletePostButton);
        return;
      }

      const commentLikeButton = event.target.closest(".commentLikeButton");
      if (commentLikeButton) {
        event.preventDefault();
        handleToggleCommentLike(commentLikeButton);
        return;
      }

      const editCommentButton = event.target.closest(".editCommentButton");
      if (editCommentButton) {
        event.preventDefault();
        handleEditComment(editCommentButton);
        return;
      }

      const deleteCommentButton = event.target.closest(".deleteCommentButton");
      if (deleteCommentButton) {
        event.preventDefault();
        handleDeleteComment(deleteCommentButton);
      }
    });
  }

  ensureSession();
}

document.addEventListener("DOMContentLoaded", initFeedActions);
