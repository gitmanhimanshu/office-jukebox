/**
 * Office Jukebox - Dedicated Player Script
 * Embedded YouTube IFrame Player for the main office speaker computer.
 * Handles official YouTube API callbacks, autoplay policies, error recovery,
 * automatic track advancement, and heartbeats.
 */

(function () {
  "use strict";

  const roomCodeMeta = document.querySelector('meta[name="room-code"]');
  const roomCode = roomCodeMeta ? roomCodeMeta.content : "";
  const csrfToken = getCookie("csrftoken");

  let player = null;
  let isPlayerReady = false;
  let currentVideoId = null;
  let heartbeatTimer = null;
  let statePollTimer = null;
  let userInteracted = false;

  const startOverlay = document.getElementById("player-start-overlay");
  const startBtn = document.getElementById("start-playback-btn");
  const skipBtn = document.getElementById("player-skip-btn");
  const playerTitle = document.getElementById("player-track-title");
  const playerChannel = document.getElementById("player-track-channel");
  const playerAddedBy = document.getElementById("player-track-addedby");
  const upNextList = document.getElementById("player-up-next-list");

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

  function showPlayerNotification(msg) {
    console.log("[Player Notification]", msg);
    const toast = document.createElement("div");
    toast.className = "toast info";
    toast.textContent = msg;
    const container = document.querySelector(".toast-container") || document.body;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  // Load YouTube IFrame Player API asynchronously
  const tag = document.createElement("script");
  tag.src = "https://www.youtube.com/iframe_api";
  const firstScriptTag = document.getElementsByTagName("script")[0];
  firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

  // Called automatically by YouTube IFrame API
  window.onYouTubeIframeAPIReady = function () {
    player = new YT.Player("youtube-player-element", {
      height: "100%",
      width: "100%",
      host: "https://www.youtube-nocookie.com",
      playerVars: {
        autoplay: 0,
        controls: 1,
        rel: 0,
        enablejsapi: 1,
        playsinline: 1,
        modestbranding: 1,
        iv_load_policy: 3,
        origin: window.location.origin,
        widget_referrer: window.location.href,
      },
      events: {
        onReady: onPlayerReady,
        onStateChange: onPlayerStateChange,
        onError: onPlayerError,
      },
    });
  };

  function onPlayerReady() {
    isPlayerReady = true;
    console.log("YouTube Player is ready.");
    startHeartbeat();
    syncPlayerWithRoom();
  }

  function onPlayerStateChange(event) {
    if (event.data === YT.PlayerState.ENDED) {
      console.log("Track finished. Advancing to next track...");
      advanceToNextTrack();
    } else if (event.data === YT.PlayerState.PLAYING) {
      sendHeartbeat(true);
    } else if (event.data === YT.PlayerState.PAUSED) {
      sendHeartbeat(false);
    }
  }

  function onPlayerError(event) {
    console.error("YouTube Player Error code:", event.data);
    // Error 100 = video not found/private, 101/150 = embedding not allowed
    showPlayerNotification("Current song is unavailable or restricted on YouTube. Skipping to next...");
    setTimeout(() => {
      advanceToNextTrack();
    }, 2000);
  }

  // Request next song from backend
  async function advanceToNextTrack() {
    if (!roomCode) return;
    try {
      const resp = await fetch(`/api/rooms/${roomCode}/player/next/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const data = await resp.json();
      if (data.success && data.has_next && data.track) {
        playTrack(data.track);
      } else {
        // Idle
        currentVideoId = null;
        if (playerTitle) playerTitle.textContent = "Waiting for songs...";
        if (playerChannel) playerChannel.textContent = "Queue is empty. Add songs from your phone or laptop!";
        if (playerAddedBy) playerAddedBy.textContent = "";
      }
    } catch (err) {
      console.error("Error advancing track:", err);
    }
  }

  function playTrack(track) {
    currentVideoId = track.video_id;
    if (playerTitle) playerTitle.textContent = track.title;
    if (playerChannel) playerChannel.textContent = track.channel_title || "";
    if (playerAddedBy) playerAddedBy.textContent = `Queued by ${track.added_by_name || "Office"}`;

    if (isPlayerReady && player) {
      if (userInteracted) {
        player.loadVideoById(track.video_id);
      } else {
        player.cueVideoById(track.video_id);
      }
    }
  }

  // Send heartbeat every 10 seconds
  function startHeartbeat() {
    clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => {
      sendHeartbeat();
    }, 10000);
  }

  async function sendHeartbeat(overridePlaying = null) {
    if (!roomCode) return;
    let position = 0;
    let isPlaying = false;

    if (isPlayerReady && player && typeof player.getCurrentTime === "function") {
      try {
        position = player.getCurrentTime() || 0;
        const state = player.getPlayerState();
        isPlaying = overridePlaying !== null ? overridePlaying : state === YT.PlayerState.PLAYING;
      } catch (e) {}
    }

    try {
      await fetch(`/api/rooms/${roomCode}/player/heartbeat/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          position_seconds: position,
          is_playing: isPlaying,
        }),
      });
    } catch (err) {
      console.warn("Heartbeat warning:", err);
    }
  }

  // Sync player state with server queue periodically
  async function syncPlayerWithRoom() {
    if (!roomCode) return;
    try {
      const resp = await fetch(`/api/rooms/${roomCode}/state/`);
      const data = await resp.json();

      if (data.success) {
        // If server has a current track and player is not playing it, load it
        if (data.current_track) {
          if (data.current_track.video_id !== currentVideoId) {
            playTrack(data.current_track);
          }
        } else if (!currentVideoId && data.queue.length > 0) {
          // Player was idle and someone queued a song
          advanceToNextTrack();
        }

        // Render mini Up Next list
        if (upNextList) {
          if (data.queue.length === 0) {
            upNextList.innerHTML = '<li class="empty-hint">No more upcoming songs</li>';
          } else {
            let html = "";
            data.queue.slice(0, 5).forEach((q) => {
              html += `
                <li class="player-queue-row">
                  <span class="pq-rank">#${q.rank}</span>
                  <div class="pq-info">
                    <span class="pq-title">${q.title}</span>
                    <span class="pq-by">added by ${q.added_by_name} • ${q.vote_count} votes</span>
                  </div>
                </li>
              `;
            });
            upNextList.innerHTML = html;
          }
        }
      }
    } catch (e) {
      console.warn("Player sync error:", e);
    } finally {
      clearTimeout(statePollTimer);
      statePollTimer = setTimeout(syncPlayerWithRoom, 4000);
    }
  }

  // Handle User Autoplay Interaction
  if (startBtn && startOverlay) {
    startBtn.addEventListener("click", () => {
      userInteracted = true;
      startOverlay.style.display = "none";
      if (isPlayerReady && player) {
        if (currentVideoId) {
          player.playVideo();
        } else {
          advanceToNextTrack();
        }
      }
    });
  }

  // Manual Skip Button on player screen
  if (skipBtn) {
    skipBtn.addEventListener("click", () => {
      if (confirm("Skip current track?")) {
        advanceToNextTrack();
      }
    });
  }
})();
