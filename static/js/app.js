/**
 * Office Jukebox - Main Dashboard Application Script
 * Vanilla JavaScript with real-time polling, debounced YouTube search,
 * queue voting, and dynamic DOM updates.
 */

(function () {
  "use strict";

  // Elements
  const roomCodeMeta = document.querySelector('meta[name="room-code"]');
  const roomCode = roomCodeMeta ? roomCodeMeta.content : "";
  const csrfToken = getCookie("csrftoken");

  let currentHash = null;
  let pollTimer = null;
  let searchTimer = null;
  let pollInterval = 3000;

  // Cache DOM nodes
  const nowPlayingThumb = document.getElementById("now-playing-thumb");
  const nowPlayingTitle = document.getElementById("now-playing-title");
  const nowPlayingChannel = document.getElementById("now-playing-channel");
  const nowPlayingAddedBy = document.getElementById("now-playing-added-by");
  const nowPlayingEqualizer = document.getElementById("now-playing-equalizer");
  const nowPlayingEmpty = document.getElementById("now-playing-empty");
  const nowPlayingActive = document.getElementById("now-playing-active");

  const queueContainer = document.getElementById("queue-items-container");
  const queueCountBadge = document.getElementById("queue-count-badge");
  const onlineCountBadge = document.getElementById("online-count-badge");
  const speakerStatusBadge = document.getElementById("speaker-status-badge");

  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  const searchSpinner = document.getElementById("search-spinner");

  const previewModal = document.getElementById("preview-modal");
  const previewIframe = document.getElementById("preview-iframe");
  const previewCloseBtn = document.getElementById("preview-close-btn");

  // Helper: Cookie getter for CSRF token
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Toast Notification System
  function showToast(message, type = "info") {
    let container = document.querySelector(".toast-container");
    if (!container) {
      container = document.createElement("div");
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Poll Room State
  async function pollRoomState() {
    if (!roomCode) return;
    try {
      const resp = await fetch(`/api/rooms/${roomCode}/state/`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!resp.ok) {
        throw new Error(`HTTP error ${resp.status}`);
      }
      const data = await resp.json();
      if (data.success) {
        if (data.settings && data.settings.poll_interval_ms) {
          pollInterval = data.settings.poll_interval_ms;
        }
        updateRoomUI(data);
      }
    } catch (err) {
      console.warn("Polling warning:", err.message);
    } finally {
      clearTimeout(pollTimer);
      pollTimer = setTimeout(pollRoomState, pollInterval);
    }
  }

  // Update DOM when state hash changes
  function updateRoomUI(data) {
    // Online count & speaker state
    if (onlineCountBadge && data.room) {
      onlineCountBadge.textContent = `${data.room.online_count} online`;
    }
    if (speakerStatusBadge && data.room) {
      if (data.room.player_online) {
        speakerStatusBadge.className = "pill-badge active";
        speakerStatusBadge.innerHTML = '<span class="status-dot online"></span> Speaker Connected';
      } else {
        speakerStatusBadge.className = "pill-badge warning";
        speakerStatusBadge.innerHTML = '<span class="status-dot offline"></span> Speaker Idle';
      }
    }

    // Skip DOM re-renders if state is identical
    if (data.hash && data.hash === currentHash) {
      return;
    }
    currentHash = data.hash;

    // Render Current Track
    if (data.current_track) {
      const track = data.current_track;
      if (nowPlayingEmpty) nowPlayingEmpty.style.display = "none";
      if (nowPlayingActive) nowPlayingActive.style.display = "flex";

      if (nowPlayingThumb) nowPlayingThumb.src = track.thumbnail_url || "";
      if (nowPlayingTitle) nowPlayingTitle.textContent = track.title;
      if (nowPlayingChannel) nowPlayingChannel.textContent = track.channel_title || "Unknown Artist";
      if (nowPlayingAddedBy) {
        nowPlayingAddedBy.textContent = `Queued by ${track.added_by_name} • ${track.duration_formatted}`;
      }
      if (nowPlayingEqualizer) {
        nowPlayingEqualizer.style.display = track.is_playing ? "flex" : "none";
      }
    } else {
      if (nowPlayingActive) nowPlayingActive.style.display = "none";
      if (nowPlayingEmpty) nowPlayingEmpty.style.display = "block";
    }

    // Render Queue Items
    if (queueContainer) {
      if (queueCountBadge) {
        queueCountBadge.textContent = `${data.queue.length} in queue`;
      }

      if (data.queue.length === 0) {
        queueContainer.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">🎵</div>
            <h3>Queue is Empty</h3>
            <p>Search for your favorite track and add it to the shared office queue!</p>
          </div>
        `;
      } else {
        let html = "";
        data.queue.forEach((item) => {
          const votedClass = item.has_voted ? "voted" : "";
          const removeBtn = item.can_remove
            ? `<button class="btn btn-icon btn-sm remove-song-btn" data-id="${item.id}" title="Remove song">✕</button>`
            : "";

          html += `
            <div class="queue-item" data-id="${item.id}">
              <div class="queue-rank">#${item.rank}</div>
              <img src="${escapeHtml(item.thumbnail_url)}" alt="thumb" class="queue-thumb" />
              <div class="queue-details">
                <div class="queue-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                <div class="queue-meta">
                  <span>${escapeHtml(item.channel_title)}</span>
                  <span>•</span>
                  <span>${escapeHtml(item.duration_formatted)}</span>
                  <span>•</span>
                  <span>by <strong>${escapeHtml(item.added_by_name)}</strong></span>
                </div>
              </div>
              <div class="queue-actions">
                <button class="vote-btn ${votedClass}" data-id="${item.id}" title="Vote for this song">
                  <span class="vote-arrow">▲</span>
                  <span class="vote-count">${item.vote_count}</span>
                </button>
                ${removeBtn}
              </div>
            </div>
          `;
        });
        queueContainer.innerHTML = html;
        bindQueueEvents();
      }
    }
  }

  // Bind Voting and Removal Events
  function bindQueueEvents() {
    if (!queueContainer) return;

    // Vote click
    queueContainer.querySelectorAll(".vote-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const itemId = btn.getAttribute("data-id");
        if (!itemId) return;

        // Optimistic UI toggle
        const isVoted = btn.classList.contains("voted");
        const countSpan = btn.querySelector(".vote-count");
        let count = parseInt(countSpan.textContent, 10) || 0;

        btn.classList.toggle("voted");
        countSpan.textContent = isVoted ? count - 1 : count + 1;

        try {
          const resp = await fetch(`/api/rooms/${roomCode}/queue/${itemId}/vote/`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken,
              "X-Requested-With": "XMLHttpRequest",
            },
          });
          const res = await resp.json();
          if (!res.success) {
            showToast(res.error || "Failed to vote", "error");
            pollRoomState(); // Revert
          } else {
            countSpan.textContent = res.vote_count;
            if (res.has_voted) {
              btn.classList.add("voted");
            } else {
              btn.classList.remove("voted");
            }
          }
        } catch (err) {
          showToast("Network error voting on song.", "error");
          pollRoomState();
        }
      });
    });

    // Remove click
    queueContainer.querySelectorAll(".remove-song-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const itemId = btn.getAttribute("data-id");
        if (!itemId || !confirm("Remove this song from the queue?")) return;

        try {
          const resp = await fetch(`/api/rooms/${roomCode}/queue/${itemId}/remove/`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken,
              "X-Requested-With": "XMLHttpRequest",
            },
          });
          const res = await resp.json();
          if (res.success) {
            showToast("Song removed from queue.", "info");
            pollRoomState();
          } else {
            showToast(res.error || "Failed to remove song.", "error");
          }
        } catch (err) {
          showToast("Network error removing song.", "error");
        }
      });
    });
  }

  // Debounced YouTube Search
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const query = searchInput.value.trim();
      clearTimeout(searchTimer);

      if (!query) {
        if (searchResults) searchResults.innerHTML = "";
        return;
      }

      if (searchSpinner) searchSpinner.style.display = "inline-block";

      searchTimer = setTimeout(async () => {
        try {
          const resp = await fetch(`/api/youtube/search/?q=${encodeURIComponent(query)}`);
          const data = await resp.json();
          if (searchSpinner) searchSpinner.style.display = "none";

          if (data.error) {
            showToast(data.error, "error");
            if (searchResults) {
              searchResults.innerHTML = `<div class="empty-state"><p>${escapeHtml(data.error)}</p></div>`;
            }
            return;
          }

          renderSearchResults(data.results || []);
        } catch (err) {
          if (searchSpinner) searchSpinner.style.display = "none";
          showToast("Search failed: Network error", "error");
        }
      }, 400);
    });
  }

  // Render Search Results List
  function renderSearchResults(items) {
    if (!searchResults) return;

    if (items.length === 0) {
      searchResults.innerHTML = `
        <div class="empty-state">
          <p>No songs found. Try another search or paste a direct YouTube video link.</p>
        </div>
      `;
      return;
    }

    let html = "";
    items.forEach((item) => {
      const itemDataAttr = encodeURIComponent(JSON.stringify(item));
      html += `
        <div class="search-item">
          <img src="${escapeHtml(item.thumbnail_url)}" alt="thumbnail" class="search-thumb" />
          <div class="search-info">
            <div class="search-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
            <div class="search-channel">${escapeHtml(item.channel_title)} • ${escapeHtml(item.duration_formatted)}</div>
          </div>
          <div class="search-actions" style="display: flex; gap: 0.5rem;">
            <button class="btn btn-secondary btn-sm preview-btn" data-video-id="${item.video_id}" title="Preview video">Preview</button>
            <button class="btn btn-primary btn-sm add-queue-btn" data-track="${itemDataAttr}">+ Add</button>
          </div>
        </div>
      `;
    });

    searchResults.innerHTML = html;

    // Bind Add Buttons
    searchResults.querySelectorAll(".add-queue-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rawData = btn.getAttribute("data-track");
        if (!rawData) return;
        const trackData = JSON.parse(decodeURIComponent(rawData));

        btn.disabled = true;
        btn.textContent = "Adding...";

        try {
          const resp = await fetch(`/api/rooms/${roomCode}/queue/add/`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken,
              "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(trackData),
          });
          const res = await resp.json();
          if (res.success) {
            showToast(res.message, "success");
            btn.textContent = "Added!";
            pollRoomState();
          } else {
            showToast(res.error || "Failed to add song.", "error");
            btn.disabled = false;
            btn.textContent = "+ Add";
          }
        } catch (err) {
          showToast("Network error adding song to queue.", "error");
          btn.disabled = false;
          btn.textContent = "+ Add";
        }
      });
    });

    // Bind Preview Buttons
    searchResults.querySelectorAll(".preview-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const videoId = btn.getAttribute("data-video-id");
        if (videoId && previewModal && previewIframe) {
          previewIframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
          previewModal.classList.add("active");
        }
      });
    });
  }

  // Preview Modal Close
  if (previewCloseBtn && previewModal && previewIframe) {
    previewCloseBtn.addEventListener("click", () => {
      previewModal.classList.remove("active");
      previewIframe.src = "";
    });
  }

  // Copy Room Code Helper
  const copyRoomBtn = document.getElementById("copy-room-code-btn");
  if (copyRoomBtn) {
    copyRoomBtn.addEventListener("click", () => {
      if (roomCode) {
        navigator.clipboard.writeText(roomCode);
        showToast(`Copied room code: ${roomCode}`, "success");
      }
    });
  }

  // Skip Song Button (if moderator on dashboard)
  const skipBtn = document.getElementById("dashboard-skip-btn");
  if (skipBtn) {
    skipBtn.addEventListener("click", async () => {
      if (!confirm("Skip the currently playing song?")) return;
      try {
        const resp = await fetch(`/api/rooms/${roomCode}/player/skip/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        const res = await resp.json();
        if (res.success) {
          showToast("Skipped track.", "info");
          pollRoomState();
        } else {
          showToast(res.error || "Failed to skip track.", "error");
        }
      } catch (e) {
        showToast("Error skipping track.", "error");
      }
    });
  }

  // Start polling on load
  if (roomCode) {
    pollRoomState();
  }
})();
