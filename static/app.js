function initCommentPosting() {
  const body = document.body;
  let currentUserId = body.dataset.currentUserId;
  let currentUsername = body.dataset.currentUsername || "you";

  function getStoredToken() {
    return window.localStorage.getItem("authToken");
  }

  function setStoredToken(token) {
    window.localStorage.setItem("authToken", token);
  }

  async function ensureToken() {
    let token = getStoredToken();
    if (token) {
      return token;
    }

    const username = window.prompt("Username:");
    if (!username) {
      return null;
    }
    const password = window.prompt("Password:");
    if (!password) {
      return null;
    }

    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const payload = await response.json();
    if (!response.ok) {
      alert(payload.error || "Login failed.");
      return null;
    }
    if (payload.user) {
      currentUsername = payload.user.username || currentUsername;
      currentUserId = payload.user.id || currentUserId;
    }
    setStoredToken(payload.token);
    return payload.token;
  }

  const sections = document.querySelectorAll(".addCommentSection");
  sections.forEach((section) => {
    const button = section.querySelector(".postCommentButton");
    const input = section.querySelector("input");
    const card = section.closest(".card");
    if (!button || !input || !card) {
      return;
    }

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const postId = card.dataset.postId;
      const text = input.value.trim();

      if (!postId) {
        alert("This post is not from the database yet.");
        return;
      }
      if (!text) {
        alert("Write a comment first.");
        return;
      }

      const token = await ensureToken();
      if (!token) {
        return;
      }

      button.setAttribute("aria-busy", "true");
      button.textContent = "Posting...";

      try {
        const response = await fetch(`/api/posts/${postId}/comments`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ text }),
        });

        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Failed to post comment.");
        }

        const commentsContainer = card.querySelector(".comments");
        if (commentsContainer) {
          const newComment = document.createElement("div");
          newComment.className = "comment";
          newComment.innerHTML = `
            <p class="postUser"><strong>${currentUsername}</strong></p>
            <p>${payload.text}</p>
          `;
          const timeEl = commentsContainer.querySelector(".postTime");
          if (timeEl) {
            commentsContainer.insertBefore(newComment, timeEl);
          } else {
            commentsContainer.appendChild(newComment);
          }
        }

        input.value = "";
      } catch (error) {
        alert(error.message);
      } finally {
        button.removeAttribute("aria-busy");
        button.textContent = "Post";
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", initCommentPosting);
