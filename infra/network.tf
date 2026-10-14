# One network for Workboard and whatever joins it later. A custom network has
# no ingress firewall rules, so nothing reaches into it from outside.
resource "google_compute_network" "main" {
  name                    = "main"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis]
}

# Cloud Run joins through this (Direct VPC egress), taking about two addresses
# per instance. A /20 leaves room for many more services.
resource "google_compute_subnetwork" "singapore" {
  name          = "singapore"
  network       = google_compute_network.main.id
  region        = local.region
  ip_cidr_range = "10.10.0.0/20"
}

# Private services access: the range Google's managed services, Cloud SQL
# among them, take their private IPs from, peered into the network.
resource "google_compute_global_address" "google_services" {
  name          = "google-services"
  network       = google_compute_network.main.id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = "10.20.0.0"
  prefix_length = 16
}

resource "google_service_networking_connection" "google_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.google_services.name]
}
