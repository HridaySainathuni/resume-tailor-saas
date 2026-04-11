// Dashboard JavaScript

let _lastResultId = null;
let _currentTab = 'resume';

// === Tab Switching ===
function switchTab(tab) {
    _currentTab = tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[onclick="switchTab('${tab}')"]`).classList.add('active');

    if (tab === 'resume') {
        document.getElementById('resume-tab-actions').style.display = 'block';
        document.getElementById('cover-letter-tab-actions').style.display = 'none';
    } else {
        document.getElementById('resume-tab-actions').style.display = 'none';
        document.getElementById('cover-letter-tab-actions').style.display = 'block';
    }
}

// === Resume Tailor ===
async function tailorResume() {
    const btn = document.getElementById('tailor-btn');
    const resume = document.getElementById('resume').value.trim();
    const jobDescription = document.getElementById('job_description').value.trim();
    const jobTitle = document.getElementById('job_title').value.trim();
    const company = document.getElementById('company').value.trim();

    if (!resume || !jobDescription) {
        showToast('Please paste both your resume and the job description.', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Tailoring... (20-30 seconds)';

    try {
        const resp = await fetch('/api/tailor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resume, job_description: jobDescription, job_title: jobTitle, company }),
        });

        const data = await resp.json();

        if (!resp.ok) {
            if (resp.status === 402) {
                if (confirm('You\'ve used all free tailors. Upgrade to Pro for $9/month?')) {
                    subscribe();
                }
                return;
            }
            showToast(data.error || 'Something went wrong', 'error');
            return;
        }

        document.getElementById('tailored-output').textContent = data.tailored_resume;
        document.getElementById('result-section').style.display = 'block';
        document.getElementById('result-section').scrollIntoView({ behavior: 'smooth' });

        _lastResultId = data.result_id;
        document.getElementById('pdf-btn').style.display = 'inline-block';
        document.getElementById('docx-btn').style.display = 'inline-block';

        // Hide compare/ats from previous run
        document.getElementById('compare-section').style.display = 'none';
        document.getElementById('ats-section').style.display = 'none';
        document.getElementById('tailored-output').style.display = 'block';

        // Update remaining count in badge
        if (data.remaining_free !== null && data.remaining_free !== undefined) {
            const badge = document.querySelector('.badge-free');
            if (badge) badge.textContent = `Free: ${data.remaining_free} left`;
        }

        showToast('Resume tailored successfully!', 'success');
        loadHistory();
    } catch (err) {
        showToast('Network error. Please try again.', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Tailor My Resume';
    }
}

// === Cover Letter ===
async function generateCoverLetter() {
    const btn = document.getElementById('cover-letter-btn');
    const resume = document.getElementById('resume').value.trim();
    const jobDescription = document.getElementById('job_description').value.trim();
    const jobTitle = document.getElementById('job_title').value.trim();
    const company = document.getElementById('company').value.trim();

    if (!resume || !jobDescription) {
        showToast('Please paste both your resume and the job description.', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Writing cover letter... (15-20 seconds)';

    try {
        const resp = await fetch('/api/cover-letter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                resume, job_description: jobDescription,
                job_title: jobTitle, company,
                result_id: _lastResultId,
            }),
        });

        const data = await resp.json();

        if (!resp.ok) {
            if (resp.status === 402) {
                if (confirm('You\'ve used all free tailors. Upgrade to Pro for $9/month?')) {
                    subscribe();
                }
                return;
            }
            showToast(data.error || 'Something went wrong', 'error');
            return;
        }

        document.getElementById('cover-letter-output').textContent = data.cover_letter;
        document.getElementById('cover-letter-section').style.display = 'block';
        document.getElementById('cover-letter-section').scrollIntoView({ behavior: 'smooth' });

        if (_lastResultId) {
            document.getElementById('cl-pdf-btn').style.display = 'inline-block';
        }

        if (data.remaining_free !== null && data.remaining_free !== undefined) {
            const badge = document.querySelector('.badge-free');
            if (badge) badge.textContent = `Free: ${data.remaining_free} left`;
        }

        showToast('Cover letter generated!', 'success');
    } catch (err) {
        showToast('Network error. Please try again.', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Generate Cover Letter';
    }
}

// === Copy ===
function copyResult() {
    const text = document.getElementById('tailored-output').textContent;
    navigator.clipboard.writeText(text).then(() => showToast('Resume copied to clipboard!', 'success'));
}

function copyCoverLetter() {
    const text = document.getElementById('cover-letter-output').textContent;
    navigator.clipboard.writeText(text).then(() => showToast('Cover letter copied!', 'success'));
}

// === Stripe ===
async function subscribe() {
    try {
        const resp = await fetch('/billing/checkout', { method: 'POST' });
        const data = await resp.json();
        if (data.checkout_url) {
            window.location.href = data.checkout_url;
        } else {
            showToast(data.error || 'Could not start checkout', 'error');
        }
    } catch (err) {
        showToast('Network error', 'error');
    }
}

async function manageSubscription() {
    try {
        const resp = await fetch('/billing/portal', { method: 'POST' });
        const data = await resp.json();
        if (data.portal_url) {
            window.location.href = data.portal_url;
        }
    } catch (err) {
        showToast('Network error', 'error');
    }
}

// === History ===
async function loadHistory() {
    try {
        const resp = await fetch('/api/history');
        if (!resp.ok) return;
        const items = await resp.json();
        const container = document.getElementById('history-list');
        if (!container) return;

        if (items.length === 0) {
            container.innerHTML = '<p class="text-muted" style="font-size: 0.9rem;">No tailored resumes yet. Try one above!</p>';
            return;
        }

        container.innerHTML = items.map(item => `
            <div class="history-item" onclick="loadResult(${item.id})">
                <div>
                    <strong>${escapeHtml(item.job_title || 'Untitled')}</strong>
                    ${item.company ? ' at ' + escapeHtml(item.company) : ''}
                    ${item.has_cover_letter ? '<span class="badge-tiny">+CL</span>' : ''}
                </div>
                <span class="history-meta">${new Date(item.created_at).toLocaleDateString()}</span>
            </div>
        `).join('');
    } catch (err) {
        // silent fail
    }
}

async function loadResult(id) {
    try {
        const resp = await fetch(`/api/history/${id}`);
        if (!resp.ok) return;
        const data = await resp.json();

        document.getElementById('resume').value = data.original_resume;
        document.getElementById('job_description').value = data.job_description;
        document.getElementById('job_title').value = data.job_title || '';
        document.getElementById('company').value = data.company || '';
        document.getElementById('tailored-output').textContent = data.tailored_resume;
        document.getElementById('result-section').style.display = 'block';
        _lastResultId = data.id;
        document.getElementById('pdf-btn').style.display = 'inline-block';
        document.getElementById('docx-btn').style.display = 'inline-block';

        // Load cover letter if exists
        if (data.cover_letter) {
            document.getElementById('cover-letter-output').textContent = data.cover_letter;
            document.getElementById('cover-letter-section').style.display = 'block';
            document.getElementById('cl-pdf-btn').style.display = 'inline-block';
        } else {
            document.getElementById('cover-letter-section').style.display = 'none';
        }

        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
        // silent fail
    }
}

// === ATS Score ===
async function runAtsScore() {
    const resume = document.getElementById('tailored-output').textContent;
    const jd = document.getElementById('job_description').value.trim();

    if (!resume || !jd) {
        showToast('Need both a tailored resume and job description to score.', 'error');
        return;
    }

    try {
        const resp = await fetch('/api/ats-score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resume, job_description: jd }),
        });
        const data = await resp.json();
        if (!resp.ok) { showToast(data.error, 'error'); return; }

        document.getElementById('ats-score-num').textContent = data.score;
        document.getElementById('ats-grade').textContent = data.grade;
        document.getElementById('ats-detail').textContent =
            `${data.matched_count}/${data.total_jd_keywords} keywords matched`;

        const circle = document.getElementById('ats-circle');
        circle.className = 'ats-score-circle';
        if (data.score >= 80) circle.classList.add('score-excellent');
        else if (data.score >= 60) circle.classList.add('score-good');
        else if (data.score >= 40) circle.classList.add('score-fair');
        else circle.classList.add('score-poor');

        document.getElementById('ats-matched').innerHTML =
            data.matched_keywords.map(k =>
                `<span class="keyword matched">${escapeHtml(k.keyword)}</span>`
            ).join('');

        document.getElementById('ats-missing').innerHTML =
            data.missing_keywords.map(k =>
                `<span class="keyword missing">${escapeHtml(k.keyword)}</span>`
            ).join('');

        document.getElementById('ats-section').style.display = 'block';
    } catch (err) {
        showToast('Error computing ATS score', 'error');
    }
}

// === Compare View ===
function toggleCompare() {
    const section = document.getElementById('compare-section');
    const single = document.getElementById('tailored-output');

    if (section.style.display === 'none') {
        document.getElementById('original-output').textContent =
            document.getElementById('resume').value;
        document.getElementById('tailored-compare').textContent =
            single.textContent;
        section.style.display = 'flex';
        single.style.display = 'none';
    } else {
        section.style.display = 'none';
        single.style.display = 'block';
    }
}

// === Downloads ===
async function downloadPdf() {
    if (!_lastResultId) { showToast('No result to download', 'error'); return; }
    window.open(`/api/download-pdf/${_lastResultId}`, '_blank');
}

async function downloadDocx() {
    if (!_lastResultId) { showToast('No result to download', 'error'); return; }
    window.open(`/api/download-docx/${_lastResultId}`, '_blank');
}

async function downloadCoverLetterPdf() {
    if (!_lastResultId) { showToast('No result to download', 'error'); return; }
    window.open(`/api/download-cover-letter/${_lastResultId}`, '_blank');
}

// === Import URL ===
function importFromUrl() {
    document.getElementById('import-modal').style.display = 'flex';
    document.getElementById('import-url').value = '';
    document.getElementById('import-url').focus();
}

function closeImportModal() {
    document.getElementById('import-modal').style.display = 'none';
}

async function doImportUrl() {
    const url = document.getElementById('import-url').value.trim();
    if (!url) { showToast('Please enter a URL', 'error'); return; }

    const btn = document.getElementById('import-btn');
    btn.disabled = true;
    btn.textContent = 'Importing...';

    try {
        const resp = await fetch('/api/import-jd', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Failed to import', 'error');
            return;
        }

        document.getElementById('job_description').value = data.text;
        if (data.title) document.getElementById('job_title').value = data.title;
        if (data.company) document.getElementById('company').value = data.company;
        closeImportModal();
        showToast('Job description imported!', 'success');
    } catch (err) {
        showToast('Failed to import from URL', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Import';
    }
}

// Close modal on outside click
document.addEventListener('click', (e) => {
    const modal = document.getElementById('import-modal');
    if (e.target === modal) closeImportModal();
});

// === Toast Notification ===
function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// === Utility ===
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Load history on page load
document.addEventListener('DOMContentLoaded', () => {
    loadHistory();

    // Check URL params for subscription status
    const params = new URLSearchParams(window.location.search);
    if (params.get('subscribed') === 'true') {
        showToast('Welcome to Pro! You now have unlimited tailors.', 'success');
        window.history.replaceState({}, '', '/dashboard');
    }
    if (params.get('cancelled') === 'true') {
        showToast('Checkout cancelled. No charges were made.', 'info');
        window.history.replaceState({}, '', '/dashboard');
    }
});
