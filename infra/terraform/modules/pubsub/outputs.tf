output "topic" {
  value = google_pubsub_topic.signals.name
}

output "topic_id" {
  value = google_pubsub_topic.signals.id
}

output "subscription" {
  value = google_pubsub_subscription.router_push.name
}

output "dead_letter_topic" {
  value = google_pubsub_topic.dead_letters.name
}
