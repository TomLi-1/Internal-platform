function initCommentPosting() {
  const body = document.body;
  const currentUserId = body.dataset.currentUserId;
  const currentUsername = body.dataset.currentUsername || "you";

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

      if (!currentUserId) {
        alert("No current user found. Seed the database first.");
        return;
      }
      if (!postId) {
        alert("This post is not from the database yet.");
        return;
      }
      if (!text) {
        alert("Write a comment first.");
        return;
      }

      button.setAttribute("aria-busy", "true");
      button.textContent = "Posting...";

      try {
        const response = await fetch(`/api/posts/${postId}/comments`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: Number(currentUserId), text }),
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
