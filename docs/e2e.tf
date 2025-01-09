terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "=4.14.0"
    }
  }
}

# If using the "az" azure cli for authentication,
# you will need `ARM_SUBSCRIPTION_ID` in the environment - see:
# https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/azure_cli
provider "azurerm" {
  features {}
}

variable "ssh_key" {
  type = string
  description = "public ssh key to be added to all created VMs (for the 'ubuntu' user)"
}

resource "azurerm_resource_group" "tailscale_testing" {
  name     = "tailscale"
  location = "Australia East"
}

resource "azurerm_virtual_network" "vnet" {
  name                = "tailscale-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name
}

resource "azurerm_subnet" "vnet_subnet" {
  name                 = "tailscale-vnet_subnet"
  resource_group_name  = azurerm_resource_group.tailscale_testing.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_public_ip" "derper" {
  name                = "derper"
  domain_name_label   = "derper"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  allocation_method   = "Static"
}

resource "azurerm_network_security_group" "derper" {
  name                = "derper-nsg"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  security_rule {
    name                       = "SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "HTTP"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "HTTPS"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "STUN"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "3478"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "ICMPInbound"
    priority                   = 140
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "ICMPOutbound"
    priority                   = 150
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "derper" {
  name                = "derper-nic"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vnet_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id = azurerm_public_ip.derper.id
  }
}

resource "azurerm_network_interface_security_group_association" "derper" {
  network_interface_id      = azurerm_network_interface.derper.id
  network_security_group_id = azurerm_network_security_group.derper.id
}

resource "azurerm_linux_virtual_machine" "derper" {
  name                = "derper"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  size                = "Standard_DS1_v2"
  admin_username      = "ubuntu"
  network_interface_ids = [
    azurerm_network_interface.derper.id,
  ]

  admin_ssh_key {
    username   = "ubuntu"
    public_key = var.ssh_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  # find these details by running `az vm image list --publisher Canonical`
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# output "derper_public_ip" {
#   description = "derper VM public ip"
#   value = resource.azurerm_linux_virtual_machine.derper.public_ip_address
# }

output "derper_vm_access" {
  description = "SSH access info for the derper VM"
  value = "ssh ${resource.azurerm_linux_virtual_machine.derper.admin_username}@${resource.azurerm_public_ip.derper.fqdn}"
}

resource "azurerm_public_ip" "headscale" {
  name                = "headscale"
  domain_name_label   = "headscale"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  allocation_method   = "Static"
}

resource "azurerm_network_security_group" "headscale" {
  name                = "headscale-nsg"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  security_rule {
    name                       = "SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "HTTP"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "HTTPS"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "headscale" {
  name                = "headscale-nic"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vnet_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id = azurerm_public_ip.headscale.id
  }
}

resource "azurerm_network_interface_security_group_association" "headscale" {
  network_interface_id      = azurerm_network_interface.headscale.id
  network_security_group_id = azurerm_network_security_group.headscale.id
}

resource "azurerm_linux_virtual_machine" "headscale" {
  name                = "headscale"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  size                = "Standard_DS1_v2"
  admin_username      = "ubuntu"
  network_interface_ids = [
    azurerm_network_interface.headscale.id,
  ]

  admin_ssh_key {
    username   = "ubuntu"
    public_key = var.ssh_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

output "headscale_vm_access" {
  description = "SSH access info for the headscale VM"
  value = "ssh ${resource.azurerm_linux_virtual_machine.headscale.admin_username}@${resource.azurerm_public_ip.headscale.fqdn}"
}

resource "azurerm_network_security_group" "tailscale" {
  name                = "tailscale-nsg"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  security_rule {
    name                       = "SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_public_ip" "tailscale_1" {
  name                = "tailscale_1"
  domain_name_label   = "tailscale-1"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  allocation_method   = "Static"
}

resource "azurerm_network_interface" "tailscale_1" {
  name                = "tailscale-1-nic"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vnet_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id = azurerm_public_ip.tailscale_1.id
  }
}

resource "azurerm_network_interface_security_group_association" "tailscale_1" {
  network_interface_id      = azurerm_network_interface.tailscale_1.id
  network_security_group_id = azurerm_network_security_group.tailscale.id
}

resource "azurerm_linux_virtual_machine" "tailscale_1" {
  name                = "tailscale-1"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  size                = "Standard_DS1_v2"
  admin_username      = "ubuntu"
  network_interface_ids = [
    azurerm_network_interface.tailscale_1.id,
  ]

  admin_ssh_key {
    username   = "ubuntu"
    public_key = var.ssh_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

output "tailscale_1_vm_access" {
  description = "SSH access info for the tailscale-1 VM"
  value = "ssh ${resource.azurerm_linux_virtual_machine.tailscale_1.admin_username}@${resource.azurerm_public_ip.tailscale_1.fqdn}"
}

resource "azurerm_public_ip" "tailscale_2" {
  name                = "tailscale_2"
  domain_name_label   = "tailscale-2"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  allocation_method   = "Static"
}

resource "azurerm_network_interface" "tailscale_2" {
  name                = "tailscale-2-nic"
  location            = azurerm_resource_group.tailscale_testing.location
  resource_group_name = azurerm_resource_group.tailscale_testing.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vnet_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id = azurerm_public_ip.tailscale_2.id
  }
}

resource "azurerm_network_interface_security_group_association" "tailscale_2" {
  network_interface_id      = azurerm_network_interface.tailscale_2.id
  network_security_group_id = azurerm_network_security_group.tailscale.id
}

resource "azurerm_linux_virtual_machine" "tailscale_2" {
  name                = "tailscale-2"
  resource_group_name = azurerm_resource_group.tailscale_testing.name
  location            = azurerm_resource_group.tailscale_testing.location
  size                = "Standard_DS1_v2"
  admin_username      = "ubuntu"
  network_interface_ids = [
    azurerm_network_interface.tailscale_2.id,
  ]

  admin_ssh_key {
    username   = "ubuntu"
    public_key = var.ssh_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

output "tailscale_2_vm_access" {
  description = "SSH access info for the tailscale-2 VM"
  value = "ssh ${resource.azurerm_linux_virtual_machine.tailscale_2.admin_username}@${resource.azurerm_public_ip.tailscale_2.fqdn}"
}

## TODO: can I use lxd provider here too for a local tailscale vm?
