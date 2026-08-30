output "bucket_name" {
  description = "Created GCS bucket name."
  value       = google_storage_bucket.this.name
}
