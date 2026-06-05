const API_BASE = 'https://clipflow-api-wd6b.onrender.com/api';

// Tab switching
const tabs = document.querySelectorAll('.tab');
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(tab.dataset.tab + '-tab').classList.add('active');
  });
});

const jobsContainer = document.getElementById('jobsContainer');
const jobs = [];

const stepsOrder = [
  { key: 'pending', label: '⏳ Queued', icon: '🕐' },
  { key: 'fetching transcript', label: '📝 Fetching transcript', icon: '📡' },
  { key: 'downloading full video', label: '⬇ Downloading video', icon: '📥' },
  { key: 'transcribing', label: '🎙️ Transcribing', icon: '🎧' },
  { key: 'selecting', label: '🎯 Finding best clip', icon: '🔍' },
  { key: 'downloading clip', label: '✂️ Downloading clip segment', icon: '📦' },
  { key: 'trimming', label: '🎬 Trimming & cropping', icon: '✂️' },
  { key: 'done', label: '✅ Completed', icon: '🎉' },
];

function createJobCard(job) {
  const card = document.createElement('div');
  card.className = 'job-card';
  card.id = 'job-' + job.id;

  const header = document.createElement('div');
  header.className = 'job-header';
  const title = document.createElement('span');
  title.className = 'job-title';
  title.textContent = job.source || job.url;
  const statusBadge = document.createElement('span');
  statusBadge.className = 'job-status ' + job.status;

  header.appendChild(title);
  header.appendChild(statusBadge);
  card.appendChild(header);

  // Progress steps
  const stepsContainer = document.createElement('div');
  stepsContainer.className = 'progress-steps';
  stepsOrder.forEach(step => {
    const stepDiv = document.createElement('div');
    stepDiv.className = 'step';
    stepDiv.id = `step-${job.id}-${step.key.replace(/\s+/g, '-')}`;
    stepDiv.innerHTML = `<span class="step-icon">${step.icon}</span><span class="step-label">${step.label}</span>`;
    stepsContainer.appendChild(stepDiv);
  });
  card.appendChild(stepsContainer);

  // Video preview placeholder
  const videoDiv = document.createElement('div');
  videoDiv.className = 'video-container';
  videoDiv.style.display = 'none';
  card.appendChild(videoDiv);

  return card;
}

function updateJobCard(job) {
  const card = document.getElementById('job-' + job.id);
  if (!card) return;

  // Update status badge
  const badge = card.querySelector('.job-status');
  badge.textContent = statusEmoji(job.status) + ' ' + job.status;
  badge.className = 'job-status ' + job.status;

  // Update progress steps
  let foundCurrent = false;
  stepsOrder.forEach(step => {
    const stepDiv = document.getElementById(`step-${job.id}-${step.key.replace(/\s+/g, '-')}`);
    if (!stepDiv) return;
    stepDiv.classList.remove('active', 'completed');
    if (step.key === job.status || (job.status === 'done' && step.key === 'done')) {
      stepDiv.classList.add('completed');
      foundCurrent = true;
    } else if (!foundCurrent && job.status !== 'error') {
      stepDiv.classList.add('completed');
    } else if (job.status === 'error' && step.key === 'error') {
      stepDiv.classList.add('error');
    }
  });
  // Highlight the current step
  if (job.status !== 'done' && job.status !== 'error') {
    const currentStepDiv = document.getElementById(`step-${job.id}-${job.status.replace(/\s+/g, '-')}`);
    if (currentStepDiv) currentStepDiv.classList.add('active');
  }

  // Show video if done
  if (job.status === 'done' && job.videoUrl) {
    const videoDiv = card.querySelector('.video-container');
    videoDiv.style.display = 'block';
    videoDiv.innerHTML = `
      <video src="${escapeHtml(job.videoUrl)}" controls></video>
      <a href="${escapeHtml(job.videoUrl)}" download class="download-btn">⬇ Download Clip</a>
    `;
  }

  // Show error message
  if (job.status === 'error' && job.error) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-msg';
    errorDiv.textContent = job.error;
    card.appendChild(errorDiv);
  }
}

// Handle URL form
document.getElementById('urlForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = document.getElementById('youtubeUrl').value.trim();
  if (!url) return;
  await submitJob({ type: 'url', url });
  document.getElementById('youtubeUrl').value = '';
});

// Handle Upload form
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('videoFile');
  const file = fileInput.files[0];
  if (!file) return;
  await submitJob({ type: 'upload', file });
  fileInput.value = '';
});

async function submitJob({ type, url, file }) {
  const localJobId = crypto.randomUUID();
  const job = {
    id: localJobId,
    source: type === 'url' ? url : file.name,
    status: 'pending',
  };
  jobs.push(job);

  const card = createJobCard(job);
  jobsContainer.prepend(card);
  updateJobCard(job);

  const submitBtns = document.querySelectorAll('button[type="submit"]');
  submitBtns.forEach(btn => btn.disabled = true);

  try {
    let backendJobId;
    if (type === 'url') {
      const res = await fetch(`${API_BASE}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ youtube_url: url }),
      });
      if (!res.ok) throw new Error('Failed to create job');
      const data = await res.json();
      backendJobId = data.id;
    } else {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/jobs/upload`, { method: 'POST', body: formData });
      if (!res.ok) throw new Error('Failed to upload');
      const data = await res.json();
      backendJobId = data.id;
    }

    // Poll for updates (fast: every 2 seconds)
    let done = false;
    while (!done) {
      await delay(2000);
      const statusRes = await fetch(`${API_BASE}/jobs/${backendJobId}`);
      if (!statusRes.ok) continue;
      const jobData = await statusRes.json();
      // Update local job with current status
      job.status = jobData.status;
      job.videoUrl = jobData.status === 'done' ? `${API_BASE.replace('/api', '')}${jobData.clip_url}` : null;
      job.error = jobData.error;
      updateJobCard(job);
      if (jobData.status === 'done' || jobData.status === 'error') {
        done = true;
      }
    }
  } catch (err) {
    job.status = 'error';
    job.error = err.message;
    updateJobCard(job);
  } finally {
    submitBtns.forEach(btn => btn.disabled = false);
  }
}

function statusEmoji(status) {
  const map = {
    pending: '🕐', 'fetching transcript': '📡', 'downloading full video': '📥',
    transcribing: '🎧', selecting: '🔍', 'downloading clip': '📦', trimming: '✂️',
    done: '✅', error: '❌',
  };
  return map[status] || '⚙️';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}