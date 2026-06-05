const API_BASE = 'https://clipflow-api-wd6b.onrender.com/api';

const form = document.getElementById('clipForm');
const fileInput = document.getElementById('videoFile');
const submitBtn = document.getElementById('submitBtn');
const jobsContainer = document.getElementById('jobsContainer');
const jobs = [];

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const localJobId = crypto.randomUUID();
  const job = { id: localJobId, fileName: file.name, status: 'pending' };
  jobs.push(job);
  renderJobs();
  fileInput.value = '';
  submitBtn.disabled = true;
  submitBtn.textContent = '⏳';

  try {
    const formData = new FormData();
    formData.append('file', file);

    const createRes = await fetch(`${API_BASE}/jobs/upload`, {
      method: 'POST',
      body: formData
    });
    if (!createRes.ok) throw new Error('Failed to create job');
    const { id: backendJobId } = await createRes.json();

    let done = false;
    updateJobStatus(localJobId, 'processing');
    while (!done) {
      await delay(3000);
      const statusRes = await fetch(`${API_BASE}/jobs/${backendJobId}`);
      if (!statusRes.ok) continue;
      const jobData = await statusRes.json();
      if (jobData.status === 'done') {
        updateJobStatus(localJobId, 'done', {
          videoUrl: `https://clipflow-api-wd6b.onrender.com${jobData.clip_url}`
        });
        done = true;
      } else if (jobData.status === 'error') {
        updateJobStatus(localJobId, 'error', { error: jobData.error });
        done = true;
      }
    }
  } catch (err) {
    updateJobStatus(localJobId, 'error', { error: err.message });
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '🔥 Clip It';
  }
});

function updateJobStatus(id, status, extra = {}) {
  const job = jobs.find(j => j.id === id);
  if (!job) return;
  job.status = status;
  if (extra.videoUrl) job.videoUrl = extra.videoUrl;
  if (extra.error) job.error = extra.error;
  renderJobs();
}

function renderJobs() {
  jobsContainer.innerHTML = jobs.map(job => `
    <div class="job-card">
      <div class="job-header">
        <span class="job-url">${escapeHtml(job.fileName || job.url)}</span>
        <span class="status ${job.status}">${statusEmoji(job.status)} ${job.status}</span>
      </div>
      ${job.status === 'processing' ? '<div class="progress-bar"><div class="fill"></div></div>' : ''}
      ${job.status === 'error' && job.error ? `<div class="error-msg">${escapeHtml(job.error)}</div>` : ''}
      ${job.status === 'done' && job.videoUrl ? `
        <div class="video-container">
          <video src="${escapeHtml(job.videoUrl)}" controls></video>
          <a href="${escapeHtml(job.videoUrl)}" download class="download-btn">⬇ Download Clip</a>
        </div>
      ` : ''}
    </div>
  `).join('');
}

function statusEmoji(status) {
  const map = { pending: '🕐', processing: '⚙️', done: '✅', error: '❌' };
  return map[status] || '';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}