# ANL:waggle-license
# This file is part of the Waggle Platform.  Please see the file
# LICENSE.waggle.txt for the legal details of the copyright and software
# license.  For more details on the Waggle project, visit:
#          http://www.wa8.gl
# ANL:waggle-license
import datetime as dt
import numpy as np
from random import randint


from bokeh.io import output_file, show
from bokeh.layouts import layout, column
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.layouts import widgetbox
from bokeh.models.widgets import CheckboxButtonGroup, Panel, Tabs

from bokeh.models import CustomJS

from bokeh.client import push_session
from bokeh.io import curdoc


sensor_unit = {
	'Temperature': 'Degree Celsius (*C)',
	'ADC_temperature': 'Degree Celsius (*C)',
	'Humidity': 'Relative Humidity (%RH)',
	'Pressure': 'Pascal (hPa)',
	'Light': 'Various Units',
	'UV_index': 'index',
	'Acceleration': 'gauss (g)',
	'Magnetic_field': 'Gauss (G)',
	'Sound': 'Voltage (needs to be converted to Decibel (dB))',
	'Abs_humidity': 'Absolute Humidity (g/kg or no unit)',
	'Temp_diff': 'Degree Celsius (*C)'
}

class data_time_Panel(object):
	
	def __init__(self, category, sensor_list, mac_list):
		self.unit = sensor_unit[category]
		self.category = category
		self.sensor_list = sensor_list
		self.mac_list = mac_list

		self.checkbox_list = sensor_list + mac_list
		self.sources = ColumnDataSource()

		self.callback = CustomJS(args=dict(source=self.sources), code="""
			var data = source.data;
			
			var f = cb_obj.active;
			var list = cb_obj.labels;

			var sensors = []
			var macs = []

			var active_list = []

			for (i = 0; i < list.length; i++) {
				if (f.indexOf(i) != -1) {
					if (list[i].charAt(0) == '_') {
						macs.push(list[i]);
					}
					else {
						sensors.push(list[i]);
					}
				}
			}

			for (i = 0; i < sensors.length;i++) {
				for (j = 0;j < macs.length; j++) {
					active_list.push(sensors[i] + macs[j]);
				}
			}

			var found = false;

			for (name in data) {
				if (name.includes("active") || name.includes("_x")) {
					continue;
				}
				for (i = 0; i < active_list.length; i++) {
					if (name.includes(active_list[i])) {
						name_active = name + "_active";
						data[name] = data[name_active];
						found = true;
						
						break;
					}
				}

				if (found == false) {
					name_inactive = name + "_inactive";
					data[name] = data[name_inactive];
				}
				else {
					found = false;
				}
			}
			source.trigger('change');
			""")


		self.cbg = CheckboxButtonGroup(
			labels=self.checkbox_list,
			active=[i for i in range(len(self.checkbox_list))],
			callback=self.callback)

		self.widget = (widgetbox(self.cbg, width = 1000))
		self.plot = figure(
			title=category,
			x_axis_type="datetime",
			x_axis_label = "Date and Time",
			y_axis_label = self.unit,
			width = 1500,
			height = 600,
			tools="pan,wheel_zoom,box_zoom,reset,save,box_select")

	def fill_source(self, name, mac, data):
		x = [ r[0] for r in data]
		y = [ r[1] for r in data]
		z = np.empty(len(x)) * np.nan
		
		self.sources.add(data=x, name=name+mac+'_x')
		self.sources.add(data=y, name=name+mac+'_y')
		self.sources.add(data=y, name=name+mac+'_y_active')
		self.sources.add(data=z, name=name+mac+'_y_inactive')

		self.plot_source(name, mac)

	def plot_source(self, name, mac):
		color_r = randint(0,255)
		color_g = randint(0,255)
		color_b = randint(0,255)

		self.plot.circle(name+mac+'_x', name+mac+'_y', 
			source = self.sources, 
			color = (color_r, color_g, color_b),
			alpha = 0.5, 
			legend = name + "_" + mac)

	def get_panel(self):
		return Panel(child = column([self.widget, self.plot]), title = self.category)
