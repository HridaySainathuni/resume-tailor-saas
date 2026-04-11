// Dashboard JavaScript

async function tailorResume() {
    const btn = document.getElementById('tailor-btn');
    const resume = document.getElementById('resume').value.trim();
    const jobDescription = document.getElementById('job_description').value.trim();
    const jobTitle = document.getElementById('job_title').value.trim();
    const company = document.getElementById('company').value.trim();

    if (!resume || !jobDescription) {
        alert('Please paste both your resume and the job description.');
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
            alert(data.error || 'Something went wrong');
            return;
        }

        document.getElementById('tailored-output').textContent = data.tailored_resume;
        document.getElementById('result-section').style.display = 'block';
        document.getElementById('result-section').scrollIntoView({ behavior: 'smooth' });

        // Enable PDF download
        _lastResultId = data.result_id;
        document.getElementById('pdf-btn').style.display = 'inline-block';

        // Hide compare/ats from previous run
        document.getElementById('compare-section').style.display = 'none';
        document.getElementById('ats-section').style.display = 'none';
        document.getElementById('tailored-output').style.display = 'block';

        loadHistory();
    } catch (err) {
        alert('Network error. Please try again.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Tailor My Resume';
    }
}

function copyResult() {
    const text = document.getElementById('tailored-output').textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = event.target;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy to Clipboard'; }, 2000);
    });
}

async function subscribe() {
    try {
        const resp = await fetch('/billing/checkout', { method: 'POST' });
        const data = await resp.json();
        if (data.checkout_url) {
            window.location.href = data.checkout_url;
        } else {
            alert(data.error || 'Could not start checkout');
        }
    } catch (err) {
        alert('Network error');
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
        alert('Network error');
    }
}

async function loadHistory() {
    try {
        const resp = await fetch('/api/history');
        if (!resp.ok) return;
        const items = await resp.json();
        const container = document.getElementById('history-list');
        if (!container) return;

        if (items.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No tailored resumes yet. Try one above!</p>';
            return;
        }

        container.innerHTML = items.map(item => `
            <div class="history-item" onclick="loadResult(${item.id})">
                <div>
                    <strong>${item.job_title || 'Untitled'}</strong>
                    ${item.company ? ' at ' + item.company : ''}
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

        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
        // silent fail
    }
}

// --- ATS Score ---
async function runAtsScore() {
    const resume = document.getElementById('tailored-output').textContent;
    const jd = document.getElementById('job_description').value.trim();

    if (!resume || !jd) {
        alert('Need both a tailored resume and job description to score.');
        return;
    }

    try {
        const resp = await fetch('/api/ats-score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resume, job_description: jd }),
        });
        const data = await resp.json();
        if (!resp.ok) { alert(data.error); return; }

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
                `<span class="keyword matched">${k.keyword}</span>`
            ).join('');

        document.getElementById('ats-missing').innerHTML =
            data.missing_keywords.map(k =>
                `<span class="keyword missing">${k.keyword}</span>`
            ).join('');

        document.getElementById('ats-section').style.display = 'block';
    } catch (err) {
        alert('Error computing ATS score');
    }
}

// --- Compare View ---
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

// --- PDF Download ---
let _lastResultId = null;

async function downloadPdf() {
    if (!_lastResultId) { alert('No result to download'); return; }
    window.open(`/api/download-pdf/${_lastResultId}`, '_blank');
}

// Load history on page load
document.addEventListener('DOMContentLoaded', loadHistory);
