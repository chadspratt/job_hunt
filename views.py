import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path

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