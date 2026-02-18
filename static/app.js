function initCommentPosting() {
  const body = document.body;
  let currentUserId = body.dataset.currentUserId;
  let currentUsername = body.dataset.currentUsername || "you";

  let currentUser = null;

  async function ensureSession() {
    if (currentUser) {
      return currentUser;
    }

    const response = await fetch("/api/auth/me", {
      credentials: "same-origin",
    });
    if (!response.ok) {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search
      );
      window.location.href = `/login?next=${next}`;
      return null;
    }
    const payload = await response.json();
    currentUser = payload;
    currentUsername = payload.username || currentUsername;
    currentUserId = payload.id || currentUserId;
    return currentUser;
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

      const session = await ensureSession();
      if (!session) {
        return;
      }

      button.setAttribute("aria-busy", "true");
      button.textContent = "Posting...";

      try {
        const response = await fetch(`/api/posts/${postId}/comments`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
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
