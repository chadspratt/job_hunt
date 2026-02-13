from django.db import models


class JobHunt(models.Model):
    class Meta:
        db_table = 'job_hunt'
        ordering = ['-created_at']

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class JobPosting(models.Model):
    class Meta:
        db_table = 'job_posting'
        ordering = ['-date_posted']

    id = models.AutoField(primary_key=True)
    job_hunt = models.ForeignKey(JobHunt, on_delete=models.CASCADE, related_name='postings')
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=500, blank=True)
    date_posted = models.DateTimeField(auto_now_add=True)
    location = models.CharField(max_length=255, blank=True)
    distance_from_home = models.FloatField(null=True, blank=True)  # in minutes
    min_salary = models.IntegerField(null=True, blank=True)
    max_salary = models.IntegerField(null=True, blank=True)
    is_remote_only = models.BooleanField(default=False)
    is_in_office_only = models.BooleanField(default=False)
    hidden = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} at {self.company}"

    @property
    def salary_display(self):
        if self.min_salary and self.max_salary:
            return f"${self.min_salary:,}–${self.max_salary:,}"
        elif self.min_salary:
            return f"${self.min_salary:,}+"
        elif self.max_salary:
            return f"Up to ${self.max_salary:,}"
        return ""

    @property
    def application(self):
        return self.applications.first()

class JobApplication(models.Model):
    class Meta:
        db_table = 'job_application'
        ordering = ['-date_applied']

    Status = models.TextChoices('Status',
        'Bookmarked Applied PhoneScreen Interview TakeHome FinalRound Offer Rejected Withdrawn')

    id = models.AutoField(primary_key=True)
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    date_applied = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=Status, default='Bookmarked')
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Application for {self.job_posting.title} at {self.job_posting.company} - {self.status}"
    
class PastEvents(models.Model):
    class Meta:
        db_table = 'past_events'
        ordering = ['-date']

    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    date = models.DateTimeField()

    def __str__(self):
        return f"{self.title} on {self.date}"
