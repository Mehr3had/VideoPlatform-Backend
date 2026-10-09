const commentForm=document.getElementById("comment-form");
const commentText=document.getElementById("comment-text");
const commentsList=document.getElementById("comments-list");
const commentSubmit=document.getElementById("comment-submit");

commentForm.addEventListener("submit", async function (event) {

    event.preventDefault();

    const text = commentText.value.trim();

    if (!text) {
        return;
    }

    const url = commentForm.action;

    const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]"
    ).value;

    commentSubmit.disabled = true;
    commentSubmit.textContent = "Posting...";

    const response = await fetch(url, {

        method: "POST",

        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken
        },

        body: JSON.stringify({
            text: text
        })

    });

    const data = await response.json();

    commentSubmit.disabled = false;
    commentSubmit.textContent = "Post Comment";

    if (response.ok) {

        const comment = data.comment;

        const commentElement = document.createElement("div");

        commentElement.classList.add("comment");

        commentElement.innerHTML = `
            <div class="comment-header">

                <strong>
                    ${comment.username}
                </strong>

                <span>
                    Just now
                </span>

            </div>

            <p>
                ${comment.text}
            </p>
        `;

        commentsList.prepend(commentElement);

        commentText.value = "";

    } else {

        alert(data.error || "Failed to add comment.");

    }

});

const reactionForm = document.getElementById("reaction-form");

const likesCount = document.getElementById("likes-count");
const dislikesCount = document.getElementById("dislikes-count");

reactionForm.addEventListener("submit", async function (event) {

    event.preventDefault();

    const reaction = event.submitter.value;

    const csrfToken = reactionForm.querySelector(
        "[name=csrfmiddlewaretoken]"
    ).value;

    const response = await fetch(
        reactionForm.action,
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },

            body: JSON.stringify({
                reaction: reaction
            })
        }
    );

    const data = await response.json();

    if (response.ok) {

        likesCount.textContent = data.likes_count;

        dislikesCount.textContent = data.dislikes_count;

        console.log(data.message);

    } else {

        alert(data.error || "Failed to react to video.");

    }

});

const shareButton = document.getElementById("share-button");
const shareMessage = document.getElementById("share-message");

shareButton.addEventListener("click", async function () {

    try {

        await navigator.clipboard.writeText(
            window.location.href
        );

        shareMessage.textContent = "✓ Link copied!";

        setTimeout(function () {
            shareMessage.textContent = "";
        }, 2000);

    } catch (error) {

        shareMessage.textContent = "Failed to copy link.";

    }

});