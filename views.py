import json
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import yaml

from django.contrib import messages
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import JobApplication, JobHunt, JobPosting, PastEvents


def _get_active_hunt(request):
    """Get the active job hunt (from query param, or default to newest)."""
    hunt_id = request.GET.get('hunt') or request.POST.get('hunt')
    if hunt_id:
        return get_object_or_404(JobHunt, id=hunt_id)
    return JobHunt.objects.first()  # ordered by -created_at


def dashboard(request):
    """Main page: show postings for the active job hunt."""
    hunt = _get_active_hunt(request)
    all_hunts = JobHunt.objects.all()

    if not hunt:
        return render(request, 'job_hunt/dashboard.html', {
            'hunt': None,
            'all_hunts': all_hunts,
            'events': PastEvents.objects.all(),
        })

    show_hidden = request.GET.get('show_hidden') == '1'
    sort = request.GET.get('sort', '-date_posted')

    allowed_sorts = {
        'title', '-title',
        'company', '-company',
        'date_posted', '-date_posted',
        'min_salary', '-min_salary',
        'max_salary', '-max_salary',
        'location', '-location',
        'distance_from_home', '-distance_from_home',
    }
    if sort not in allowed_sorts:
        sort = '-date_posted'

    postings = JobPosting.objects.filter(job_hunt=hunt).prefetch_related('applications')
    if not show_hidden:
        postings = postings.filter(hidden=False)
    postings = postings.order_by(sort)

    return render(request, 'job_hunt/dashboard.html', {
        'hunt': hunt,
        'all_hunts': all_hunts,
        'postings': postings,
        'current_sort': sort,
        'show_hidden': show_hidden,
        'hunt_id_str': str(hunt.id),
        'statuses': JobApplication.Status,
        'events': PastEvents.objects.all(),
    })


def create_hunt(request):
    """Create a new job hunt."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        target_date = request.POST.get('target_date') or None
        if name:
            hunt = JobHunt.objects.create(
                name=name,
                description=description,
                target_date=target_date,
            )
            messages.success(request, f'Job hunt "{hunt.name}" created.')
            return redirect(f'/job_hunt/?hunt={hunt.id}')
        else:
            messages.error(request, 'Name is required.')
    return redirect('/job_hunt/')


def create_posting(request):
    """Add a new job posting to the active hunt."""
    if request.method == 'POST':
        hunt_id = request.POST.get('hunt')
        hunt = get_object_or_404(JobHunt, id=hunt_id)
        posting = JobPosting.objects.create(
            job_hunt=hunt,
            title=request.POST.get('title', '').strip(),
            company=request.POST.get('company', '').strip(),
            description=request.POST.get('description', '').strip(),
            url=request.POST.get('url', '').strip(),
            location=request.POST.get('location', '').strip(),
            distance_from_home=request.POST.get('distance_from_home') or None,
            min_salary=request.POST.get('min_salary') or None,
            max_salary=request.POST.get('max_salary') or None,
            is_remote_only=request.POST.get('is_remote_only') == 'on',
            is_in_office_only=request.POST.get('is_in_office_only') == 'on',
        )
        messages.success(request, f'Posting "{posting.title}" added.')
        return redirect(f'/job_hunt/?hunt={hunt.id}')
    return redirect('/job_hunt/')


def edit_posting(request, posting_id):
    """Edit an existing job posting."""
    posting = get_object_or_404(JobPosting, id=posting_id)
    if request.method == 'POST':
        posting.title = request.POST.get('title', '').strip()
        posting.company = request.POST.get('company', '').strip()
        posting.description = request.POST.get('description', '').strip()
        posting.url = request.POST.get('url', '').strip()
        posting.location = request.POST.get('location', '').strip()
        posting.distance_from_home = request.POST.get('distance_from_home') or None
        posting.min_salary = request.POST.get('min_salary') or None
        posting.max_salary = request.POST.get('max_salary') or None
        posting.is_remote_only = request.POST.get('is_remote_only') == 'on'
        posting.is_in_office_only = request.POST.get('is_in_office_only') == 'on'
        posting.save()
        messages.success(request, f'Posting "{posting.title}" updated.')
        return redirect(f'/job_hunt/?hunt={posting.job_hunt_id}')

    return render(request, 'job_hunt/edit_posting.html', {
        'posting': posting,
        'hunt': posting.job_hunt,
    })


def toggle_posting_hidden(request, posting_id):
    """Toggle the hidden state of a posting."""
    posting = get_object_or_404(JobPosting, id=posting_id)
    posting.hidden = not posting.hidden
    posting.save()
    action = 'hidden' if posting.hidden else 'unhidden'
    messages.success(request, f'Posting "{posting.title}" {action}.')
    return redirect(f'/job_hunt/?hunt={posting.job_hunt_id}')


def create_application(request, posting_id):
    """Create or update an application for a posting."""
    posting = get_object_or_404(JobPosting, id=posting_id)
    if request.method == 'POST':
        application = posting.applications.first()
        status = request.POST.get('status', 'Bookmarked')
        notes = request.POST.get('notes', '').strip()
        if application:
            application.status = status
            application.notes = notes
            application.save()
            messages.success(request, f'Application for "{posting.title}" updated.')
        else:
            JobApplication.objects.create(
                job_posting=posting,
                status=status,
                notes=notes,
            )
            messages.success(request, f'Application for "{posting.title}" created.')
        return redirect(f'/job_hunt/?hunt={posting.job_hunt_id}')
    return redirect('/job_hunt/')


def edit_application(request, application_id):
    """Edit an existing application."""
    application = get_object_or_404(JobApplication, id=application_id)
    if request.method == 'POST':
        application.status = request.POST.get('status', application.status)
        application.notes = request.POST.get('notes', '').strip()
        application.save()
        messages.success(request, 'Application updated.')
        return redirect(f'/job_hunt/?hunt={application.job_posting.job_hunt_id}')

    return render(request, 'job_hunt/edit_application.html', {
        'application': application,
        'hunt': application.job_posting.job_hunt,
        'statuses': JobApplication.Status,
    })


def create_event(request):
    """Create a new past event."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        date_str = request.POST.get('date', '').strip()
        
        if title and date_str:
            try:
                event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                PastEvents.objects.create(title=title, date=event_date)
                messages.success(request, 'Event added.')
            except ValueError:
                messages.error(request, 'Invalid date format.')
        else:
            messages.error(request, 'Title and date are required.')
    
    return redirect('/job_hunt/')


_CV_BUILDER_DIR = Path(__file__).resolve().parent / 'cv_builder'
_CV_PDF_PATH = _CV_BUILDER_DIR / 'src' / 'rendered' / 'moderncv.pdf'

# Module-level state for async resume build (fine for single-process dev server)
_resume_state = {'status': 'idle', 'error': ''}
_resume_lock = threading.Lock()


def _run_resume_build():
    """Background thread: run the cv_builder Docker pipeline."""
    rendered_dir = _CV_BUILDER_DIR / 'src' / 'rendered'
    rendered_dir.mkdir(exist_ok=True)
    try:
        for cmd, label in [
            (['docker', 'compose', 'build', 'composer'], 'Docker build'),
            (['docker', 'compose', '-p', 'cv', 'run', '--rm', 'composer', 'python', 'main.py'], 'Resume render'),
            (['docker', 'compose', '-p', 'cv', 'run', '--rm', 'windmill', 'latexmk', '-pdf'], 'PDF build'),
        ]:
            r = subprocess.run(
                cmd, cwd=_CV_BUILDER_DIR,
                capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                with _resume_lock:
                    _resume_state['status'] = 'error'
                    _resume_state['error'] = f'{label} failed: {(r.stderr or r.stdout)[-500:]}'
                return

        if not _CV_PDF_PATH.exists():
            with _resume_lock:
                _resume_state['status'] = 'error'
                _resume_state['error'] = 'PDF was not produced. Check the cv_builder output.'
            return

        with _resume_lock:
            _resume_state['status'] = 'done'
    except subprocess.TimeoutExpired:
        with _resume_lock:
            _resume_state['status'] = 'error'
            _resume_state['error'] = 'Resume generation timed out (>10 min).'
    except FileNotFoundError:
        with _resume_lock:
            _resume_state['status'] = 'error'
            _resume_state['error'] = 'Docker was not found. Ensure Docker Desktop is running.'


@require_POST
def generate_resume(request):
    """Kick off the cv_builder pipeline in a background thread."""
    with _resume_lock:
        if _resume_state['status'] == 'building':
            return JsonResponse({'status': 'building'})
        _resume_state['status'] = 'building'
        _resume_state['error'] = ''
    threading.Thread(target=_run_resume_build, daemon=True).start()
    return JsonResponse({'status': 'building'})


def resume_status(request):
    """Return the current build status as JSON."""
    with _resume_lock:
        return JsonResponse(dict(_resume_state))


def download_resume(request):
    """Serve the generated PDF."""
    if not _CV_PDF_PATH.exists():
        messages.error(request, 'No resume PDF found. Generate one first.')
        return redirect('/job_hunt/?tab=resume')
    return FileResponse(
        open(_CV_PDF_PATH, 'rb'),
        content_type='application/pdf',
        as_attachment=False,
        filename='resume.pdf',
    )


_POSTINGS_DIR = Path(__file__).resolve().parent / 'job_postings'

# Per-posting state: {posting_id: {'status': ..., 'error': ''}}
_posting_resume_states: dict = {}
_posting_resume_lock = threading.Lock()


def _run_posting_resume_build(posting_id: int, posting_dir: Path):
    """Background thread: build a resume for a specific job posting."""
    rendered_dir = _CV_BUILDER_DIR / 'src' / 'rendered'
    rendered_dir.mkdir(exist_ok=True)
    posting_data_yml = posting_dir / 'data.yml'
    # Mount the posting's data.yml directly into the container so the original is never touched.
    data_yml_mount = f'{posting_data_yml.resolve()}:/app/data.yml'

    try:
        for cmd, label in [
            (['docker', 'compose', 'build', 'composer'], 'Docker build'),
            (['docker', 'compose', '-p', 'cv', 'run', '--rm', '-v', data_yml_mount, 'composer', 'python', 'main.py'], 'Resume render'),
            (['docker', 'compose', '-p', 'cv', 'run', '--rm', 'windmill', 'latexmk', '-pdf'], 'PDF build'),
        ]:
            r = subprocess.run(
                cmd, cwd=_CV_BUILDER_DIR,
                capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                with _posting_resume_lock:
                    _posting_resume_states[posting_id] = {
                        'status': 'error',
                        'error': f'{label} failed: {(r.stderr or r.stdout)[-500:]}',
                    }
                return

        if not (_CV_BUILDER_DIR / 'src' / 'rendered' / 'moderncv.pdf').exists():
            with _posting_resume_lock:
                _posting_resume_states[posting_id] = {
                    'status': 'error',
                    'error': 'PDF was not produced. Check the cv_builder output.',
                }
            return

        # Copy all rendered artifacts to the posting directory
        for artifact in rendered_dir.iterdir():
            shutil.copy2(artifact, posting_dir / artifact.name)

        with _posting_resume_lock:
            _posting_resume_states[posting_id] = {'status': 'done', 'error': ''}

    except subprocess.TimeoutExpired:
        with _posting_resume_lock:
            _posting_resume_states[posting_id] = {
                'status': 'error',
                'error': 'Resume generation timed out (>10 min).',
            }
    except FileNotFoundError:
        with _posting_resume_lock:
            _posting_resume_states[posting_id] = {
                'status': 'error',
                'error': 'Docker was not found. Ensure Docker Desktop is running.',
            }


@require_POST
def generate_posting_resume(request, posting_id):
    """Kick off a per-posting resume build in a background thread."""
    get_object_or_404(JobPosting, id=posting_id)

    posting_dir = _POSTINGS_DIR / str(posting_id)
    posting_dir.mkdir(exist_ok=True)

    # Seed data.yml from cv_builder/src/data.yml if not already present
    src_data_yml = _CV_BUILDER_DIR / 'src' / 'data.yml'
    posting_data_yml = posting_dir / 'data.yml'
    if not posting_data_yml.exists():
        shutil.copy2(src_data_yml, posting_data_yml)

    with _posting_resume_lock:
        if _posting_resume_states.get(posting_id, {}).get('status') == 'building':
            return JsonResponse({'status': 'building'})
        _posting_resume_states[posting_id] = {'status': 'building', 'error': ''}

    threading.Thread(
        target=_run_posting_resume_build,
        args=(posting_id, posting_dir),
        daemon=True,
    ).start()
    return JsonResponse({'status': 'building'})


def posting_resume_status(request, posting_id):
    """Return the current build status for a posting's resume."""
    with _posting_resume_lock:
        state = _posting_resume_states.get(posting_id, {'status': 'idle', 'error': ''})
    return JsonResponse(dict(state))


def download_posting_resume(request, posting_id):
    """Serve the generated PDF for a posting."""
    pdf_path = _POSTINGS_DIR / str(posting_id) / 'moderncv.pdf'
    if not pdf_path.exists():
        return JsonResponse({'error': 'No PDF found. Generate one first.'}, status=404)
    return FileResponse(
        open(pdf_path, 'rb'),
        content_type='application/pdf',
        as_attachment=False,
        filename=f'resume-posting-{posting_id}.pdf',
    )


def resume_config(request, posting_id):
    """Return base data.yml config with current posting selections (GET)."""
    get_object_or_404(JobPosting, id=posting_id)

    base_data_yml = _CV_BUILDER_DIR / 'src' / 'data.yml'
    with open(base_data_yml, 'r', encoding='utf-8') as f:
        base_data = yaml.safe_load(f)

    posting_dir = _POSTINGS_DIR / str(posting_id)
    posting_data_yml = posting_dir / 'data.yml'

    selected_skills = None
    selected_experience = None
    selected_projects = None
    selected_open_source = None

    if posting_data_yml.exists():
        with open(posting_data_yml, 'r', encoding='utf-8') as f:
            posting_data = yaml.safe_load(f) or {}
        if 'skills' in posting_data:
            selected_skills = {s['name'] for s in posting_data.get('skills', [])}
        if 'experience' in posting_data:
            selected_experience = {e['place'] for e in posting_data.get('experience', [])}
        if 'projects' in posting_data:
            selected_projects = {p['name'] for p in posting_data.get('projects', [])}
        if 'openSource' in posting_data:
            selected_open_source = {o['name'] for o in posting_data.get('openSource', [])}

    skills = [
        {'name': s['name'], 'checked': selected_skills is None or s['name'] in selected_skills}
        for s in base_data.get('skills', [])
    ]
    experience = [
        {'place': e['place'], 'checked': selected_experience is None or e['place'] in selected_experience}
        for e in base_data.get('experience', [])
    ]
    projects = [
        {'name': p['name'], 'checked': selected_projects is None or p['name'] in selected_projects}
        for p in base_data.get('projects', [])
    ]
    open_source = [
        {'name': o['name'], 'checked': selected_open_source is None or o['name'] in selected_open_source}
        for o in base_data.get('openSource', [])
    ]

    return JsonResponse({
        'skills': skills,
        'experience': experience,
        'projects': projects,
        'openSource': open_source,
    })


@require_POST
def save_resume_config(request, posting_id):
    """Save filtered data.yml for a posting based on selected items."""
    get_object_or_404(JobPosting, id=posting_id)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    selected_skills = set(data.get('skills', []))
    selected_experience = set(data.get('experience', []))
    selected_projects = set(data.get('projects', []))
    selected_open_source = set(data.get('openSource', []))

    base_data_yml = _CV_BUILDER_DIR / 'src' / 'data.yml'
    with open(base_data_yml, 'r', encoding='utf-8') as f:
        base_data = yaml.safe_load(f)

    filtered = {
        'personal': base_data.get('personal'),
        'education': base_data.get('education'),
        'skills': [s for s in base_data.get('skills', []) if s['name'] in selected_skills],
        'experience': [e for e in base_data.get('experience', []) if e['place'] in selected_experience],
        'projects': [p for p in base_data.get('projects', []) if p['name'] in selected_projects],
        'openSource': [o for o in base_data.get('openSource', []) if o['name'] in selected_open_source],
    }
    for key in ('freeformQA',):
        if key in base_data:
            filtered[key] = base_data[key]

    posting_dir = _POSTINGS_DIR / str(posting_id)
    posting_dir.mkdir(exist_ok=True)
    posting_data_yml = posting_dir / 'data.yml'

    with open(posting_data_yml, 'w', encoding='utf-8') as f:
        yaml.dump(filtered, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return JsonResponse({'success': True})


@require_POST
def update_event(request, event_id):
    """Update an event's date to now."""
    try:
        data = json.loads(request.body)
        event = get_object_or_404(PastEvents, id=event_id)
        
        if data.get('set_to_now'):
            event.date = timezone.now()
            event.save()
            return JsonResponse({'success': True})
        
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})