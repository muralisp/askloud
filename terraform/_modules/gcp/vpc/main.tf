terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~>5.0" }
  }
}

# TODO: google_compute_network, google_compute_subnetwork (with secondary IP ranges),
#        google_compute_router, google_compute_router_nat (Cloud NAT for private nodes)
