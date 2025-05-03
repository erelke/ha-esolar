# Home Assistant SAJ eSolar _Elekeeper_ Custom Integration

![elekeeper](https://github.com/erelke/ha-esolar/blob/main/images/elekeeper.png)

This integration is based on [faanskit/ha-esolar](https://github.com/faanskit/ha-esolar). It is adapted to my needs. If you need it, use it.

This version is based on the new _Elekeeper_ app and the new SAJ portal. It uses password encryption and signing of api requests. I extracted the necessary keys from the SAJ portal source code. This can change at any time and then this integration will not work. Until then, use it.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=erelke&repository=ha-esolar&category=integration)

[![Donate](https://img.shields.io/badge/Donate-BuyMeCoffe-green.svg)](https://www.buymeacoffee.com/erelke)

Integration:

![integration](https://github.com/erelke/ha-esolar/blob/main/images/ee_3.png)

Config options:

![config](https://github.com/erelke/ha-esolar/blob/main/images/ee_4.png)

Sensors:

![sensors](https://github.com/erelke/ha-esolar/blob/main/images/ee_1.png)

Diagnostics:

![diagnostics](https://github.com/erelke/ha-esolar/blob/main/images/ee_2.png)


## Bug report & Development requests & diagnostics data

In case of an error or improvement request, please send the diagnostic data as well. See the image:

![diagnostics data](https://github.com/erelke/ha-esolar/blob/main/images/ee_6.png)




---

# Home Assistant SAJ eSolar Custom Integration
This integration uses cloud polling from the SAJ eSolar portal using a reverse engineered private API. 
Thanks to [SAJ eSolar](https://github.com/djansen1987/SAJeSolar) for inspiration.

This integration today support SAJ R5 and SAJ H1. SAJ SEC has not yet been implemented mainly due to lack of access to a SEC system,

The focus on this integration is to reduce the amount of sensors published while at the same time maximize the information available and provide them as attributes. 

As an example, the H1 Inverter Power sensor has 50 information elements (15 x 3 + 5) published as attributes. This is a bit against the nature of Home Assistant development, but given a system comprising two plants, one R5 and two H1 - the amount of sensors would easly be in the hundreds. Therefore, this integration aims to publish only what is relevant as sensors.

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/attributes.png)

These attributes can be fetched by implementing a template sensor using jinja2. An example of that can be found in the advanced section below.

# Installation
### HACS
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=erelke&repository=ha-esolar&category=integration)

### Manual
- Copy directory `custom_components/saj_esolar_air` to your `<config dir>/custom_components` directory.
- Restart Home-Assistant.

## Enable the integration
Go to Settings / Devices & Services / Integrations. Click **+ ADD INTERATION**

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_step_1.png)

Search for eSolar and click on it

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_step_2.png)

Enter your SAJ eSolar username and password

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_step_3.png)

If you have more than one site, select which of the sites that shall be installed

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_step_4.png)

Following a succesful installation, a device per plant will be created

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_step_5.png)

You can see that a number of devices and entites has been created at the SAJ eSolar integration

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_done_1.PNG)

If you click on the devices, you can see this also in the Devices section

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_done_2.png)

Your home screen will now have a number of new entities depending on your system. A R5 system will have two sensors (Status and Energy) and a H1 System will have five sensors (Status, Sell Energy, Buy, Energy, Charge Energy, Discharge Energy)

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/setup_done_3.png)

## Configuration
If you need more sensor and more detailed attributes in the sensors, you can configure the integration as follows

Go to Settings / Devices & Services / SAL eSolar. Click **CONFIGURE**.

Select if you want additional inverter sensors and if you want Photovoltaics and Grid attributes.
Take note that the Photovoltaics and Grid attributes will pull additional data from the SAJ servers.

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/configure_step_1.png)

After the configuration is done you need to restart the integration. Click **...** and select **Reload**

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/configure_step_2.png)

The system will now reload and add two-tre new sensors per inverter (Energy Total, Power and for H1 system Battery SoC)

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/configure_step_3.png)

## Final result
When the system is fully set up it can look something like this

![alt text](https://github.com/erelke/ha-esolar/blob/main/images/all_done.png)

# Advanced
### Creating a template sensor based on sensor attributes.
The below example will fetch the battery direction from the inverter energy total sensor and publish that as a new sensor
```
template:
  - sensor:
      - name: "Battery Direction"
        unique_id: inverter_ass111111111111111_energy_total_battery_direction
        state: >
          {{state_attr('sensor.inverter_ass111111111111111_energy_total', 'Battery Direction')}}
```
# Donations
I mainly did this project as a learning experience for myself and have no expectations from anyone.

If you like what have been done here and want to help I would recommend that you firstly look into supporting Home
Assistant. 

You can do this by purchasing some swag from their [store](https://teespring.com/stores/home-assistant-store)
or paying for a Nabu Casa subscription. None of this could happen without them.

After you have done that if you still feel this work has been valuable to you I welcome your support through BuyMeACoffee.

<a href="https://www.buymeacoffee.com/erelke"><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=erelke&button_colour=FFDD00&font_colour=000000&font_family=Poppins&outline_colour=000000&coffee_colour=ffffff"></a>