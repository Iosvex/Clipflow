const form = document.getElementById('clipForm');
const input = document.getElementById('youtubeUrl');
const submitBtn = document.getElementById('submitBtn');
const jobsContainer = document.getElementById('jobsContainer');
const jobs = [];

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = input.value.trim();
  if (!url) return;
  const jobId = crypto.randomUUID();
  const job = { id: jobId, url, status: 'pending' };
  jobs.push(job);
  renderJobs();
  input.value = '';
  submitBtn.disabled = true;
  submitBtn.textContent = '⏳';
  try {
    updateJobStatus(jobId, 'processing');
    await delay(3000);
    updateJobStatus(jobId, 'done', { videoUrl: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4' });
  } catch (err) {
    updateJobStatus(jobId, 'error', { error: 'Something went wrong' });
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
        <span class="job-url">${escapeHtml(job.url)}</span>
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