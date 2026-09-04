terraform {
  required_version = ">= 1.5.0"

  backend "local" {}

  required_providers {
    lxd = {
      source  = "terraform-lxd/lxd"
      version = "3.0.2"
    }
  }
}

provider "lxd" {
  remote {
    name    = "local"
    address = "unix://"
  }
}

locals {
  project_name  = "tailscale-e2e"
  image         = "ubuntu:24.04"
  services_cidr = "10.210.10.0/24"
  users_cidr    = "10.210.20.0/24"

  networks = {
    services = {
      name         = "tse2es"
      acl_name     = "tailscale-e2e-services-acl"
      cidr         = local.services_cidr
      host_address = cidrhost(local.services_cidr, 1)
      blocked_cidr = local.users_cidr
    }
    users = {
      name         = "tse2eu"
      acl_name     = "tailscale-e2e-users-acl"
      cidr         = local.users_cidr
      host_address = cidrhost(local.users_cidr, 1)
      blocked_cidr = local.services_cidr
    }
  }

  instances = {
    headscale = {
      nics = {
        eth0 = { network = "services", address = cidrhost(local.services_cidr, 10) }
        eth1 = { network = "users", address = cidrhost(local.users_cidr, 10) }
      }
    }
    derper = {
      nics = {
        eth0 = { network = "services", address = cidrhost(local.services_cidr, 11) }
        eth1 = { network = "users", address = cidrhost(local.users_cidr, 11) }
      }
    }
    internal-1 = {
      nics = {
        eth0 = { network = "services", address = cidrhost(local.services_cidr, 20) }
      }
    }
    user-1 = {
      nics = {
        eth0 = { network = "users", address = cidrhost(local.users_cidr, 20) }
      }
    }
    user-2 = {
      nics = {
        eth0 = { network = "users", address = cidrhost(local.users_cidr, 21) }
      }
    }
  }

  cloud_init = "#cloud-config\n${yamlencode({
    package_update = true
    packages = [
      "snapd",
      "openssh-server",
      "curl",
      "ca-certificates",
      "netcat-openbsd",
    ]
    write_files = [{
      path        = "/etc/sysctl.d/99-e2e-no-forwarding.conf"
      permissions = "0644"
      content     = <<-EOT
        net.ipv4.ip_forward = 0
        net.ipv6.conf.all.forwarding = 0
        net.ipv6.conf.default.forwarding = 0
      EOT
    }]
    runcmd = [
      ["systemctl", "enable", "--now", "snapd.socket"],
      ["systemctl", "enable", "--now", "ssh"],
      ["sysctl", "--system"],
    ]
  })}"
}

resource "lxd_project" "e2e" {
  name        = local.project_name
  description = "Tailscale snap end-to-end test topology"

  config = {
    "features.profiles" = "true"
    "features.networks" = "false"
  }
}

resource "lxd_network_acl" "segment" {
  for_each = local.networks

  name = each.value.acl_name

  depends_on = [lxd_project.e2e]

  egress = [{
    action      = "reject"
    destination = each.value.blocked_cidr
    state       = "enabled"
  }]
}

resource "lxd_network" "segment" {
  for_each = local.networks

  name = each.value.name
  type = "bridge"

  config = {
    "dns.mode"                             = "managed"
    "ipv4.address"                         = "${each.value.host_address}/${split("/", each.value.cidr)[1]}"
    "ipv4.nat"                             = "true"
    "ipv6.address"                         = "none"
    "ipv6.nat"                             = "false"
    "security.acls"                        = lxd_network_acl.segment[each.key].name
    "security.acls.default.ingress.action" = "allow"
    "security.acls.default.egress.action"  = "allow"
  }
}

resource "lxd_profile" "e2e" {
  name    = "e2e"
  project = lxd_project.e2e.name

  config = {
    "security.nesting" = "true"
  }

  device {
    name = "root"
    type = "disk"

    properties = {
      path = "/"
      pool = "default"
    }
  }

  device {
    name = "tun"
    type = "unix-char"

    properties = {
      source = "/dev/net/tun"
      path   = "/dev/net/tun"
    }
  }
}

resource "lxd_instance" "node" {
  for_each = local.instances

  name     = each.key
  project  = lxd_project.e2e.name
  image    = local.image
  profiles = [lxd_profile.e2e.name]

  timeouts = {
    create = "15m"
  }

  config = {
    "cloud-init.user-data" = local.cloud_init
    "cloud-init.network-config" = yamlencode({
      version = 2
      ethernets = {
        for name in keys(each.value.nics) : name => {
          dhcp4 = true
          dhcp4-overrides = {
            use-dns     = !(name == "eth1" && length(each.value.nics) > 1)
            use-domains = false
            use-routes  = !(name == "eth1" && length(each.value.nics) > 1)
          }
          dhcp6        = false
          "link-local" = []
        }
      }
    })
  }

  execs = {
    cloud-init-ready = {
      command       = ["cloud-init", "status", "--wait"]
      trigger       = "once"
      fail_on_error = true
      record_output = true
    }
  }

  dynamic "device" {
    for_each = each.value.nics

    content {
      name = device.key
      type = "nic"

      properties = {
        name           = device.key
        network        = lxd_network.segment[device.value.network].name
        "ipv4.address" = device.value.address
      }
    }
  }
}

output "topology" {
  description = "LXD project and network topology."
  value = {
    project_name          = lxd_project.e2e.name
    hosts                 = local.instances
    networks              = { for name, network in lxd_network.segment : name => network.name }
    network_acls          = { for name, acl in lxd_network_acl.segment : name => acl.name }
    services_cidr         = local.services_cidr
    services_host_address = local.networks.services.host_address
    users_cidr            = local.users_cidr
    users_host_address    = local.networks.users.host_address
  }
}
