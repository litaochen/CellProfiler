'''<b>Edit Objects Manually</b> allows you to remove specific objects
from each image by pointing and clicking
<hr>

This module allows you to remove specific objects via a user interface 
where you point and click to select objects for removal. The
module displays three images: the objects as originally identified,
the objects that have not been removed, and the objects that have been
removed.

If you click on an object in the "not removed" image, it moves to the
"removed" image and will be removed. If you click on an object in the
"removed" image, it moves to the "not removed" image and will not be
removed. Clicking on an object in the original image 
toggles its "removed" state.

The pipeline pauses once per processed image when it reaches this module.
You must press the <i>Continue</i> button to accept the selected objects
and continue the pipeline.

<h4>Available measurements</h4>
<i>Image features:</i>
<ul>
<li><i>Count:</i> The number of edited objects in the image.</li>
</ul>
<i>Object features:</i>
<ul>
<li><i>Location_X, Location_Y:</i> The pixel (X,Y) coordinates of the center of mass of the edited objects.</li>
</ul>

See also <b>FilterObjects</b>, <b>MaskObject</b>, <b>OverlayOutlines</b>, <b>ConvertToImage</b>.
'''
# CellProfiler is distributed under the GNU General Public License.
# See the accompanying file LICENSE for details.
# 
# Copyright (c) 2003-2009 Massachusetts Institute of Technology
# Copyright (c) 2009-2012 Broad Institute
# 
# Please see the AUTHORS file for credits.
# 
# Website: http://www.cellprofiler.org
#
# Some matplotlib interactive editing code is derived from the sample:
#
# http://matplotlib.sourceforge.net/examples/event_handling/poly_editor.html
#
# Copyright 2008, John Hunter, Darren Dale, Michael Droettboom
# 

__version__="$Revision$"

import numpy as np

import cellprofiler.preferences as cpprefs
import cellprofiler.cpmodule as cpm
import cellprofiler.measurements as cpmeas
import cellprofiler.objects as cpo
import cellprofiler.cpimage as cpi
import cellprofiler.settings as cps
import cellprofiler.workspace as cpw
from cellprofiler.cpmath.outline import outline

import identify as I

###########################################
#
# Choices for the "do you want to renumber your objects" setting
#
###########################################
R_RENUMBER = "Renumber"
R_RETAIN = "Retain"

class EditObjectsManually(I.Identify):
    category = "Object Processing"
    variable_revision_number = 2
    module_name = 'EditObjectsManually'
    
    def create_settings(self):
        """Create your settings by subclassing this function
        
        create_settings is called at the end of initialization.
        
        You should create the setting variables for your module here:
            # Ask the user for the input image
            self.image_name = cellprofiler.settings.ImageNameSubscriber(...)
            # Ask the user for the name of the output image
            self.output_image = cellprofiler.settings.ImageNameProvider(...)
            # Ask the user for a parameter
            self.smoothing_size = cellprofiler.settings.Float(...)
        """
        self.object_name = cps.ObjectNameSubscriber("Select the objects to be edited", "None",
                                                    doc="""
            Choose a set of previously identified objects
            for editing, such as those produced by one of the
            <b>Identify</b> modules.""")
        
        self.filtered_objects = cps.ObjectNameProvider(
            "Name the edited objects","EditedObjects",
            doc="""What do you want to call the objects that remain
            after editing? These objects will be available for use by
            subsequent modules.""")
        
        self.wants_outlines = cps.Binary(
            "Retain outlines of the edited objects?", False,
            doc="""Check this box if you want to keep images of the outlines
            of the objects that remain after editing. This image
            can be saved by downstream modules or overlayed on other images
            using the <b>OverlayOutlines</b> module.""")
        
        self.outlines_name = cps.OutlineNameProvider(
            "Name the outline image", "EditedObjectOutlines",
            doc="""<i>(Used only if you have selected to retain outlines of edited objects)</i><br>
            What do you want to call the outline image?""")
        
        self.renumber_choice = cps.Choice(
            "Numbering of the edited objects",
            [R_RENUMBER, R_RETAIN],
            doc="""Choose how to number the objects that 
            remain after editing, which controls how edited objects are associated with their predecessors:
            <p>
            If you choose <i>Renumber</i>,
            this module will number the objects that remain 
            using consecutive numbers. This
            is a good choice if you do not plan to use measurements from the
            original objects and you only want to use the edited objects in downstream modules; the
            objects that remain after editing will not have gaps in numbering
            where removed objects are missing.
            <p>
            If you choose <i>Retain</i>,
            this module will retain each object's original number so that the edited object's number matches its original number. This allows any measurements you make from 
            the edited objects to be directly aligned with measurements you might 
            have made of the original, unedited objects (or objects directly 
            associated with them).""")
        
        self.wants_image_display = cps.Binary(
            "Display a guiding image?", True,
            doc = """Check this setting to display an image and outlines
            of the objects. Leave the setting unchecked if you do not
            want a guide image while editing""")
        
        self.image_name = cps.ImageNameSubscriber(
            "Select the guiding image", "None",
            doc = """
            <i>(Used only if a guiding image is desired)</i><br>
            This is the image that will appear when editing objects.
            Choose an image supplied by a previous module.""")
    
    def settings(self):
        """Return the settings to be loaded or saved to/from the pipeline
        
        These are the settings (from cellprofiler.settings) that are
        either read from the strings in the pipeline or written out
        to the pipeline. The settings should appear in a consistent
        order so they can be matched to the strings in the pipeline.
        """
        return [self.object_name, self.filtered_objects, self.wants_outlines,
                self.outlines_name, self.renumber_choice, 
                self.wants_image_display, self.image_name]
    
    def is_interactive(self):
        return True
    
    def visible_settings(self):
        """The settings that are visible in the UI
        """
        #
        # Only display the outlines_name if wants_outlines is true
        #
        result = [self.object_name, self.filtered_objects, self.wants_outlines]
        if self.wants_outlines:
            result.append(self.outlines_name)
        result += [ self.renumber_choice, self.wants_image_display]
        if self.wants_image_display:
            result += [self.image_name]
        return result
    
    def run(self, workspace):
        """Run the module
        
        workspace    - The workspace contains
            pipeline     - instance of cpp for this run
            image_set    - the images in the image set being processed
            object_set   - the objects (labeled masks) in this image set
            measurements - the measurements for this run
            frame        - the parent frame to whatever frame is created. None means don't draw.
        """
        orig_objects_name = self.object_name.value
        filtered_objects_name = self.filtered_objects.value
        
        orig_objects = workspace.object_set.get_objects(orig_objects_name)
        assert isinstance(orig_objects, cpo.Objects)
        orig_labels = orig_objects.segmented
        mask = orig_labels != 0

        if workspace.frame is None:
            # Accept the labels as-is
            filtered_labels = orig_labels
        else:
            filtered_labels = self.filter_objects(workspace, orig_labels)
        #
        # Renumber objects consecutively if asked to do so
        #
        unique_labels = np.unique(filtered_labels)
        unique_labels = unique_labels[unique_labels != 0]
        object_count = len(unique_labels)
        if self.renumber_choice == R_RENUMBER:
            mapping = np.zeros(1 if len(unique_labels) == 0 else np.max(unique_labels)+1, int)
            mapping[unique_labels] = np.arange(1,object_count + 1)
            filtered_labels = mapping[filtered_labels]
        #
        # Make the objects out of the labels
        #
        filtered_objects = cpo.Objects()
        filtered_objects.segmented = filtered_labels
        filtered_objects.unedited_segmented = orig_objects.unedited_segmented
        filtered_objects.parent_image = orig_objects.parent_image
        workspace.object_set.add_objects(filtered_objects, 
                                         filtered_objects_name)
        #
        # Add parent/child & other measurements
        #
        m = workspace.measurements
        child_count, parents = orig_objects.relate_children(filtered_objects)
        m.add_measurement(filtered_objects_name,
                          I.FF_PARENT%(orig_objects_name),
                          parents)
        m.add_measurement(orig_objects_name,
                          I.FF_CHILDREN_COUNT%(filtered_objects_name),
                          child_count)
        #
        # The object count
        #
        I.add_object_count_measurements(m, filtered_objects_name,
                                        object_count)
        #
        # The object locations
        #
        I.add_object_location_measurements(m, filtered_objects_name,
                                           filtered_labels)
        #
        # Outlines if we want them
        #
        if self.wants_outlines:
            outlines_name = self.outlines_name.value
            outlines = outline(filtered_labels)
            outlines_image = cpi.Image(outlines.astype(bool))
            workspace.image_set.add(outlines_name, outlines_image)
        #
        # Do the drawing here
        #
        if workspace.frame is not None:
            figure = workspace.create_or_find_figure(title="EditObjectsManually, image cycle #%d"%(
                workspace.measurements.image_set_number),subplots=(2,1))
            figure.subplot_imshow_labels(0, 0, orig_labels, orig_objects_name)
            figure.subplot_imshow_labels(1, 0, filtered_labels,
                                         filtered_objects_name,
                                         sharex = figure.subplot(0,0),
                                         sharey = figure.subplot(0,0))
            
    def filter_objects(self, workspace, orig_labels):
        import wx
        import matplotlib
        from matplotlib.lines import Line2D
        from matplotlib.path import Path
        from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
        from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg
        import scipy.ndimage
        from cellprofiler.gui.cpfigure import renumber_labels_for_display
        from cellprofiler.icons import get_builtin_image
        from cellprofiler.cpmath.cpmorphology import polygon_lines_to_mask
        from cellprofiler.cpmath.cpmorphology import convex_hull_image
        from cellprofiler.cpmath.cpmorphology import distance2_to_line
        
        assert isinstance(workspace,cpw.Workspace)
        class FilterObjectsDialog(wx.Dialog):
            resume_id = wx.NewId()
            cancel_id = wx.NewId()
            keep_all_id = wx.NewId()
            remove_all_id = wx.NewId()
            reverse_select = wx.NewId()
            epsilon = 5 # maximum pixel distance to a vertex for hit test
            SPLIT_PICK_FIRST_MODE = "split1"
            SPLIT_PICK_SECOND_MODE = "split2"
            NORMAL_MODE = "normal"
            #
            # The object_number for an artist
            #
            K_LABEL = "label"
            #
            # Whether the artist has been edited
            #
            K_EDITED = "edited"
            #
            # Whether the artist is on the outside of the object (True)
            # or is the border of a hole (False)
            #
            K_OUTSIDE = "outside"
            def __init__(self, module, workspace, orig_labels):
                assert isinstance(module, EditObjectsManually)
                assert isinstance(workspace, cpw.Workspace)
                #
                # Get the labels matrix and make a mask of objects to keep from it
                #
                #
                # Display a UI for choosing objects
                #
                style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
                wx.Dialog.__init__(self, workspace.frame, -1,
                                   "Choose objects to keep",
                                   style = style)
                self.module = module
                self.workspace = workspace
                self.orig_labels = orig_labels
                self.labels = orig_labels.copy()
                self.artists = {}
                self.active_artist = None
                self.active_index = None
                self.mode = self.NORMAL_MODE
                self.split_artist = None
                self.wants_image_display = module.wants_image_display.value
                self.pressed_keys = set()
                self.to_keep = np.ones(np.max(orig_labels) + 1, bool)
                self.build_ui()
                self.init_labels()
                self.display()
                self.Fit()
                
            def build_ui(self):
                sizer = wx.BoxSizer(wx.VERTICAL)
                self.SetSizer(sizer)
                self.figure = matplotlib.figure.Figure()
                self.panel = FigureCanvasWxAgg(self, -1, self.figure)
                sizer.Add(self.panel, 1, wx.EXPAND)
        
                toolbar = NavigationToolbar2WxAgg(self.panel)
                sizer.Add(toolbar, 0, wx.EXPAND)
                #
                # Make 3 axes
                #
                self.orig_axes = self.figure.add_subplot(2, 2, 1)
                self.orig_axes.set_zorder(1) # preferentially select on click.
                self.orig_axes._adjustable = 'box-forced'
                self.keep_axes = self.figure.add_subplot(
                    2, 2, 2, sharex = self.orig_axes, sharey = self.orig_axes)
                self.remove_axes = self.figure.add_subplot(
                    2, 2, 4, sharex = self.orig_axes, sharey = self.orig_axes)
                for axes in (self.orig_axes, self.keep_axes, self.remove_axes):
                    axes._adjustable = 'box-forced'
                orig_objects_name = self.module.object_name.value
                self.orig_objects_title = "Original: %s" % orig_objects_name
                for axes, title in (
                    (self.orig_axes, 
                     self.orig_objects_title),
                    (self.keep_axes, "Objects to keep"),
                    (self.remove_axes, "Objects to remove")):
                    axes.set_title(title,
                                   fontname=cpprefs.get_title_font_name(),
                                   fontsize=cpprefs.get_title_font_size())
            
                self.info_axes = self.figure.add_subplot(2, 2, 3)
                self.info_axes.set_axis_off()

                #
                # This text is available if you press the help button.
                #
                ui_text = ("Keep or remove objects by clicking\n"
                           "on them with the left mouse button.\n\n"
                           "Select an object for editing by clicking on it\n"
                           "with the right mouse button, then click on it\n"
                           "again with the right mouse button when editing\n"
                           "is complete.\n\n"
                           "Press the 1 key to toggle between one display\n"
                           "(the editing display) and three.\n\n"
                           "Press the J key to join all selected objects\n"
                           "into a single object.\n\n"
                           "Press the C key to enlarge the selected object\n"
                           "to the convex hull around it.\n\n"
                           "Press the A key to add a control point to the\n"
                           "line nearest the cursor.\n\n"
                           "Press the D key to delete the control point\n"
                           "nearest to the cursor\n\n"
                           "Press the N key to make a new object at the cursor\n"
                           "Press the S key to split, then pick two control\n"
                           "points to split an object in two\n"
                           "Esc cancels the current edit.\n\n"
                           'Press the "Done" button when editing is complete.')
                sub_sizer = wx.BoxSizer(wx.HORIZONTAL)
                #
                # Need padding on top because tool bar is wonky about its height
                #
                sizer.Add(sub_sizer, 0, wx.EXPAND | wx.TOP, 10)
                        
                #########################################
                #
                # Buttons for keep / remove / toggle
                #
                #########################################
                
                keep_button = wx.Button(self, self.keep_all_id, "Keep all")
                sub_sizer.Add(keep_button, 0, wx.ALIGN_CENTER)
        
                remove_button = wx.Button(self, self.remove_all_id, "Remove all")
                sub_sizer.Add(remove_button,0, wx.ALIGN_CENTER)
        
                toggle_button = wx.Button(self, self.reverse_select, 
                                          "Reverse selection")
                sub_sizer.Add(toggle_button,0, wx.ALIGN_CENTER)
                reset_button = wx.Button(self, -1, "Reset")
                reset_button.SetToolTipString(
                    "Undo all editing and restore the original objects")
                sub_sizer.Add(reset_button)
                self.Bind(wx.EVT_BUTTON, self.on_toggle, toggle_button)
                self.Bind(wx.EVT_BUTTON, self.on_keep, keep_button)
                self.Bind(wx.EVT_BUTTON, self.on_remove, remove_button)
                self.Bind(wx.EVT_BUTTON, self.on_reset, reset_button)
        
                ######################################
                #
                # Buttons for resume and cancel
                #
                ######################################
                button_sizer = wx.StdDialogButtonSizer()
                resume_button = wx.Button(self, self.resume_id, "Done")
                button_sizer.AddButton(resume_button)
                sub_sizer.Add(button_sizer, 0, wx.ALIGN_CENTER)
                def on_resume(event):
                    self.EndModal(wx.OK)
                self.Bind(wx.EVT_BUTTON, on_resume, resume_button)
                button_sizer.SetAffirmativeButton(resume_button)
        
                cancel_button = wx.Button(self, self.cancel_id, "Cancel")
                button_sizer.AddButton(cancel_button)
                def on_cancel(event):
                    self.EndModal(wx.CANCEL)
                self.Bind(wx.EVT_BUTTON, on_cancel, cancel_button)
                button_sizer.SetNegativeButton(cancel_button)
                button_sizer.AddButton(wx.Button(self, wx.ID_HELP))
                def on_help(event):
                    wx.MessageBox(ui_text, 
                                  caption = "Help for editing objects",
                                  parent = self)
                self.Bind(wx.EVT_BUTTON, on_help, id= wx.ID_HELP)
                                  
                button_sizer.Realize()
                if self.module.wants_image_display:
                    #
                    # Note: the checkbutton must have a reference or it
                    #       will cease to be checkable.
                    #
                    self.display_image_checkbox = matplotlib.widgets.CheckButtons(
                        self.info_axes, ["Display image"], [True])
                    self.display_image_checkbox.labels[0].set_size("small")
                    r = self.display_image_checkbox.rectangles[0]
                    rwidth = r.get_width()
                    rheight = r.get_height()
                    rx, ry = r.get_xy()
                    new_rwidth = rwidth / 2 
                    new_rheight = rheight / 2
                    new_rx = rx + rwidth/2
                    new_ry = ry + rheight/4
                    r.set_width(new_rwidth)
                    r.set_height(new_rheight)
                    r.set_xy((new_rx, new_ry))
                    l1, l2 = self.display_image_checkbox.lines[0]
                    l1.set_data((np.array((new_rx, new_rx+new_rwidth)),
                                 np.array((new_ry, new_ry+new_rheight))))
                    l2.set_data((np.array((new_rx, new_rx+new_rwidth)),
                                 np.array((new_ry + new_rheight, new_ry))))
                    
                    self.display_image_checkbox.on_clicked(
                        self.on_display_image_clicked)
                self.figure.canvas.mpl_connect('button_press_event', 
                                               self.on_click)
                self.figure.canvas.mpl_connect('draw_event', self.draw_callback)
                self.figure.canvas.mpl_connect('button_release_event',
                                               self.on_mouse_button_up)
                self.figure.canvas.mpl_connect('motion_notify_event',
                                               self.on_mouse_moved)
                self.figure.canvas.mpl_connect('key_press_event',
                                               self.on_key_down)
                self.figure.canvas.mpl_connect('key_release_event',
                                               self.on_key_up)
                
            def on_display_image_clicked(self, event):
                self.wants_image_display = not self.wants_image_display
                self.display()
                
            def init_labels(self):
                #########################################
                #
                # Construct a stable label index transform
                # and a color display image.
                #
                #########################################
                
                clabels = renumber_labels_for_display(self.labels)
                nlabels = len(self.to_keep) - 1
                label_map = np.zeros(nlabels + 1, clabels.dtype)
                label_map[self.labels.flatten()] = clabels.flatten()
                outlines = outline(clabels)
                self.oi, self.oj = np.argwhere(outlines != 0).transpose()
                self.ol = self.labels[self.oi, self.oj]
                
                cm = matplotlib.cm.get_cmap(cpprefs.get_default_colormap())
                cm.set_bad((0,0,0))
            
                mappable = matplotlib.cm.ScalarMappable(cmap=cm)
                mappable.set_clim(1, nlabels+1)
                self.colormap = mappable.to_rgba(np.arange(nlabels + 1))[:, :3]
                self.colormap = self.colormap[label_map, :]
                self.oc = self.colormap[self.ol, :]
                
            ################### d i s p l a y #######
            #
            # The following is a function that we can call to refresh
            # the figure's appearance based on the mask and the original labels
            #
            ##########################################
            
            def display(self):
                orig_objects_name = self.module.object_name.value
                if len(self.orig_axes.images) > 0:
                    # Save zoom and scale if coming through here a second time
                    x0, x1 = self.orig_axes.get_xlim()
                    y0, y1 = self.orig_axes.get_ylim()
                    set_lim = True
                else:
                    set_lim = False
                for axes, keep in (
                    (self.orig_axes, np.ones(self.to_keep.shape, bool)),
                    (self.keep_axes, self.to_keep),
                    (self.remove_axes, ~ self.to_keep)):
                    
                    assert isinstance(axes, matplotlib.axes.Axes)
                    axes.clear()
                    if self.wants_image_display:
                        image = self.workspace.image_set.get_image(
                            self.module.image_name.value)
                        image = image.pixel_data.astype(np.float)
                        image, _ = cpo.size_similarly(self.orig_labels, image)
                        if image.ndim == 2:
                            image = np.dstack((image, image, image))
                        cimage = image.copy()
                    else:
                        cimage = np.zeros(
                            (self.orig_labels.shape[0],
                             self.orig_labels.shape[1],
                             3), np.float)
                    kmask = keep[self.ol]
                    cimage[self.oi[kmask], self.oj[kmask], :] = self.oc[kmask, :]
                    axes.imshow(cimage)
                self.set_orig_axes_title()
                self.keep_axes.set_title("Objects to keep",
                                         fontname=cpprefs.get_title_font_name(),
                                         fontsize=cpprefs.get_title_font_size())
                self.remove_axes.set_title("Objects to remove",
                                           fontname=cpprefs.get_title_font_name(),
                                           fontsize=cpprefs.get_title_font_size())
                if set_lim:
                    self.orig_axes.set_xlim((x0, x1))
                    self.orig_axes.set_ylim((y0, y1))
                for artist in self.artists:
                    self.orig_axes.add_line(artist)
                if self.split_artist is not None:
                    self.orig_axes.add_line(self.split_artist)
                self.figure.canvas.draw()
                self.panel.Refresh()
                
            def draw_callback(self, event):
                '''Decorate the drawing with the animated artists'''
                self.background = self.figure.canvas.copy_from_bbox(self.orig_axes.bbox)
                for artist in self.artists:
                    self.orig_axes.draw_artist(artist)
                self.figure.canvas.blit(self.orig_axes.bbox)
                
            def get_control_point(self, event):
                '''Find the artist and control point under the cursor
                
                returns tuple of artist, and index of control point or None, None
                '''
                best_d = np.inf
                best_artist = None
                best_index = None
                for artist in self.artists:
                    data = artist.get_xydata()[:-1, :]
                    xy = artist.get_transform().transform(data)
                    x, y = xy.transpose()
                    d = np.sqrt((x-event.x)**2 + (y-event.y)**2)
                    idx = np.atleast_1d(np.argmin(d)).flatten()[0]
                    d = d[idx]
                    if d < self.epsilon and d < best_d:
                        best_d = d
                        best_artist = artist
                        best_index = idx
                return best_artist, best_index
                    
            def on_click(self, event):
                if event.inaxes not in (
                    self.orig_axes, self.keep_axes, self.remove_axes):
                    return
                if event.inaxes.get_navigate_mode() is not None:
                    return
                if self.mode == self.SPLIT_PICK_FIRST_MODE:
                    self.on_split_first_click(event)
                    return
                elif self.mode == self.SPLIT_PICK_SECOND_MODE:
                    self.on_split_second_click(event)
                    return
                if event.inaxes == self.orig_axes and event.button == 1:
                    best_artist, best_index = self.get_control_point(event)
                    if best_artist is not None:
                        self.active_artist = best_artist
                        self.active_index = best_index
                        return
                elif event.inaxes == self.orig_axes and event.button == 3:
                    for artist in self.artists:
                        path = Path(artist.get_xydata())
                        if path.contains_point((event.xdata, event.ydata)):
                            self.close_label(self.artists[artist][self.K_LABEL])
                            return
                x = int(event.xdata)
                y = int(event.ydata)
                if (x < 0 or x >= self.orig_labels.shape[1] or
                    y < 0 or y >= self.orig_labels.shape[0]):
                    return
                lnum = self.labels[y,x]
                if lnum == 0:
                    return
                if event.button == 1:
                    # Move object into / out of working set
                    if event.inaxes == self.orig_axes:
                        self.to_keep[lnum] = not self.to_keep[lnum]
                    elif event.inaxes == self.keep_axes:
                        self.to_keep[lnum] = False
                    else:
                        self.to_keep[lnum] = True
                    self.display()
                elif event.button == 3:
                    self.make_control_points(lnum)
            
            def on_key_down(self, event):
                self.pressed_keys.add(event.key)
                if event.key == "1":
                    self.toggle_single_panel(event)
                    return
                if self.mode == self.NORMAL_MODE:
                    if event.key == "j":
                        self.join_objects(event)
                    elif event.key == "c":
                        self.convex_hull(event)
                    elif event.key == "a":
                        self.add_control_point(event)
                    elif event.key == "d":
                        self.delete_control_point(event)
                    elif event.key == "n":
                        self.new_object(event)
                    elif event.key == "s":
                        self.enter_split_mode(event)
                    elif event.key == "escape":
                        self.remove_artists(event)
                elif self.mode in (self.SPLIT_PICK_FIRST_MODE, 
                                   self.SPLIT_PICK_SECOND_MODE):
                    if event.key == "escape":
                        self.exit_split_mode(event)
            
            def on_key_up(self, event):
                if event.key in self.pressed_keys:
                    self.pressed_keys.remove(event.key)
            
            def on_mouse_button_up(self, event):
                self.active_artist = None
                self.active_index = None
                
            def on_mouse_moved(self, event):
                if self.active_artist is not None:
                    self.handle_mouse_moved_active_mode(event)
                elif self.mode == self.SPLIT_PICK_SECOND_MODE:
                    self.handle_mouse_moved_pick_second_mode(event)
                    
            def handle_mouse_moved_active_mode(self, event):
                if event.inaxes != self.orig_axes:
                    return
                #
                # Don't let the user make any lines that cross other lines
                # in this object.
                #
                object_number = self.artists[self.active_artist][self.K_LABEL]
                data = [d[:-1] for d in self.active_artist.get_data()]
                n_points = len(data[0])
                before_index = (n_points - 1 + self.active_index) % n_points
                after_index = (self.active_index + 1) % n_points
                before_pt, after_pt = [
                    np.array([data[0][idx], data[1][idx]]) 
                             for idx in (before_index, after_index)]
                new_pt = np.array([event.xdata, event.ydata], int)
                path = Path(np.array((before_pt, new_pt, after_pt)))
                eps = np.finfo(np.float32).eps
                for artist in self.artists:
                    if self.artists[artist][self.K_LABEL] != object_number:
                        continue
                    if artist == self.active_artist:
                        if n_points <= 4:
                            continue
                        # Exclude the lines -2 and 2 before and after ours.
                        #
                        xx, yy = [np.hstack((d[self.active_index:],
                                             d[:(self.active_index+1)]))
                                  for d in data]
                        xx, yy = xx[2:-2], yy[2:-2]
                        xydata = np.column_stack((xx, yy))
                    else:
                        xydata = artist.get_xydata()
                    other_path = Path(xydata)
                    
                    l0 = xydata[:-1, :]
                    l1 = xydata[1:, :]
                    neww_pt = np.ones(l0.shape) * new_pt[np.newaxis, :]
                    d = distance2_to_line(neww_pt, l0, l1)
                    different_sign = (np.sign(neww_pt - l0) != 
                                      np.sign(neww_pt - l1))
                    on_segment = ((d < eps) & different_sign[:, 0] & 
                                  different_sign[:, 1])
                        
                    if any(on_segment):
                        # it's ok if the point is on the line.
                        continue
                    if path.intersects_path(other_path, filled = False):
                        return
                 
                data = self.active_artist.get_data()   
                data[0][self.active_index] = event.xdata
                data[1][self.active_index] = event.ydata
                
                #
                # Handle moving the first point which is the
                # same as the last and they need to be moved together.
                # The last should never be moved.
                #
                if self.active_index == 0:
                    data[0][-1] = event.xdata
                    data[1][-1] = event.ydata
                self.active_artist.set_data(data)
                self.artists[self.active_artist]['edited'] = True
                self.update_artists()
                
            def update_artists(self):
                self.figure.canvas.restore_region(self.background)
                for artist in self.artists:
                    self.orig_axes.draw_artist(artist)
                if self.split_artist is not None:
                    self.orig_axes.draw_artist(self.split_artist)
                self.figure.canvas.blit(self.orig_axes.bbox)
                
            def toggle_single_panel(self, event):
                for ax in (self.keep_axes, self.info_axes, self.remove_axes):
                    ax.set_visible(not ax.get_visible())
                if self.keep_axes.get_visible():
                    self.orig_axes.change_geometry(2,2,1)
                else:
                    self.orig_axes.change_geometry(1,1,1)
                self.figure.canvas.draw()
                
            def join_objects(self, event):
                all_labels = np.unique([
                    v[self.K_LABEL] for v in self.artists.values()])
                if len(all_labels) < 2:
                    return
                assert all_labels[0] == np.min(all_labels)
                for label in all_labels:
                    self.close_label(label, display=False)
                
                keep_to_keep = np.ones(len(self.to_keep), bool)
                keep_to_keep[all_labels[1:]] = False
                self.to_keep = self.to_keep[keep_to_keep]
                #
                # Renumber the labels matrix, changing the other labels'
                # label numbers to the primary one and renumbering so
                # labels appear consecutively.
                #
                renumbering = np.ones(len(keep_to_keep), self.labels.dtype)
                renumbering[keep_to_keep] = \
                    np.arange(np.sum(keep_to_keep), dtype = self.labels.dtype)
                renumbering[~keep_to_keep] = all_labels[0]
                self.labels = renumbering[self.labels]
                self.init_labels()
                self.make_control_points(all_labels[0])
                self.display()
                return all_labels[0]
                
            def convex_hull(self, event):
                if len(self.artists) == 0:
                    return
                
                all_labels = np.unique([
                    v[self.K_LABEL] for v in self.artists.values()])
                for label in all_labels:
                    self.close_label(label, display=False)
                object_number = all_labels[0]
                if len(all_labels) > 1:
                    keep_to_keep = np.ones(len(self.to_keep), bool)
                    keep_to_keep[all_labels[1:]] = False
                    self.to_keep = self.to_keep[keep_to_keep]
                    #
                    # Renumber the labels matrix, changing the other labels'
                    # label numbers to the primary one and renumbering so
                    # labels appear consecutively.
                    #
                    renumbering = np.ones(len(keep_to_keep), self.labels.dtype)
                    renumbering[keep_to_keep] = \
                        np.arange(np.sum(keep_to_keep), dtype = self.labels.dtype)
                    renumbering[~keep_to_keep] = object_number
                    self.labels = renumbering[self.labels]
                    
                mask = convex_hull_image(self.labels == object_number)
                self.labels[mask] = object_number
                self.init_labels()
                self.make_control_points(object_number)
                self.display()
            
            def add_control_point(self, event):
                if len(self.artists) == 0:
                    return
                pt_i, pt_j = event.ydata, event.xdata
                best_artist = None
                best_index = None
                best_distance = np.inf
                new_pt = None
                for artist in self.artists:
                    l = artist.get_xydata()[:, ::-1]
                    l0 = l[:-1, :]
                    l1 = l[1:, :]
                    llen = np.sqrt(np.sum((l1 - l0) ** 2, 1))
                    # the unit vector
                    v = (l1 - l0) / llen[:, np.newaxis]
                    pt = np.ones(l0.shape, l0.dtype)
                    pt[:, 0] = pt_i
                    pt[:, 1] = pt_j
                    #
                    # Project l0<->pt onto l0<->l1. If the result
                    # is longer than l0<->l1, then the closest point is l1.
                    # If the result is negative, then the closest point is l0.
                    # In either case, don't add.
                    #
                    proj = np.sum(v * (pt - l0), 1)
                    d2 = distance2_to_line(pt, l0, l1)
                    d2[proj <= 0] = np.inf
                    d2[proj >= llen] = np.inf
                    best = np.argmin(d2)
                    if best_distance > d2[best]:
                        best_distance = d2[best]
                        best_artist = artist
                        best_index = best
                        new_pt = (l0[best_index, :] + 
                                  proj[best_index, np.newaxis] * v[best_index, :])
                if best_artist is None:
                    return
                l = best_artist.get_xydata()[:, ::-1]
                l = np.vstack((l[:(best_index+1)], new_pt.reshape(1,2),
                               l[(best_index+1):]))
                best_artist.set_data((l[:, 1], l[:, 0]))
                self.artists[best_artist][self.K_EDITED] = True
                self.update_artists()
            
            def delete_control_point(self, event):
                best_artist, best_index = self.get_control_point(event)
                if best_artist is not None:
                    l = best_artist.get_xydata()
                    if len(l) < 4:
                        best_artist.remove()
                        del self.artists[best_artist]
                    else:
                        l = np.vstack((l[:best_index, :], l[(best_index+1):, :]))
                        best_artist.set_data((l[:, 0], l[:, 1]))
                        self.artists[best_artist][self.K_EDITED] = True
                    self.update_artists()
                    
            def new_object(self, event):
                object_number = len(self.to_keep)
                temp = np.ones(object_number+1, bool)
                temp[:-1] = self.to_keep
                self.to_keep = temp
                angles = np.pi * 2 * np.arange(13) / 12
                x = 20 * np.cos(angles) + event.xdata
                y = 20 * np.sin(angles) + event.ydata
                x[x < 0] = 0
                x[x >= self.labels.shape[1]] = self.labels.shape[1]-1
                y[y >= self.labels.shape[0]] = self.labels.shape[0]-1
                self.init_labels()
                new_artist = Line2D(x, y,
                                    marker='o', markerfacecolor='r',
                                    markersize=6,
                                    color=self.colormap[object_number, :],
                                    animated = True)
                
                self.artists[new_artist] = { self.K_LABEL: object_number,
                                             self.K_EDITED: True,
                                             self.K_OUTSIDE: True}
                self.display()
                
            def remove_artists(self, event):
                for artist in self.artists:
                    artist.remove()
                self.artists = {}
                self.update_artists()
                
            ################################
            #
            # Split mode
            #
            ################################
                
            SPLIT_PICK_FIRST_TITLE = "Pick first point for split or hit Esc to exit"
            SPLIT_PICK_SECOND_TITLE = "Pick second point for split or hit Esc to exit"
            
            def set_orig_axes_title(self):
                title = (
                    self.orig_objects_title if self.mode == self.NORMAL_MODE
                    else self.SPLIT_PICK_FIRST_TITLE 
                    if self.mode == self.SPLIT_PICK_FIRST_MODE
                    else self.SPLIT_PICK_SECOND_TITLE)
                self.orig_axes.set_title(
                    title,
                    fontname=cpprefs.get_title_font_name(),
                    fontsize=cpprefs.get_title_font_size())
                
            def enter_split_mode(self, event):
                self.mode = self.SPLIT_PICK_FIRST_MODE
                self.set_orig_axes_title()
                self.figure.canvas.draw()
                
            def exit_split_mode(self, event):
                if self.mode == self.SPLIT_PICK_SECOND_MODE:
                    self.split_artist.remove()
                    self.split_artist = None
                    self.update_artists()
                self.mode = self.NORMAL_MODE
                self.set_orig_axes_title()
                self.figure.canvas.draw()
                
            def on_split_first_click(self, event):
                if event.inaxes != self.orig_axes:
                    return
                pick_artist, pick_index = self.get_control_point(event)
                if pick_artist is None:
                    return
                x, y = pick_artist.get_data()
                x, y = x[pick_index], y[pick_index]
                self.split_pick_artist = pick_artist
                self.split_pick_index = pick_index
                self.split_artist = Line2D(np.array((x, x)), 
                                           np.array((y, y)),
                                           color = "blue",
                                           animated = True)
                self.orig_axes.add_line(self.split_artist)
                self.mode = self.SPLIT_PICK_SECOND_MODE
                self.set_orig_axes_title()
                self.figure.canvas.draw()
                
            def handle_mouse_moved_pick_second_mode(self, event):
                if event.inaxes == self.orig_axes:
                    x, y = self.split_artist.get_data()
                    x[1] = event.xdata
                    y[1] = event.ydata
                    self.split_artist.set_data((x, y))
                    pick_artist, pick_index = self.get_control_point(event)
                    if pick_artist is not None and self.ok_to_split(
                        pick_artist, pick_index):
                        self.split_artist.set_color("red")
                    else:
                        self.split_artist.set_color("blue")
                    self.update_artists()
                    
            def ok_to_split(self, pick_artist, pick_index):
                if (self.artists[pick_artist][self.K_LABEL] != 
                    self.artists[self.split_pick_artist][self.K_LABEL]):
                    # Second must be same object as first.
                    return False
                if pick_artist == self.split_pick_artist:
                    min_index, max_index = [
                        fn(pick_index, self.split_pick_index)
                        for fn in (min, max)]
                    if max_index - min_index < 2:
                        # don't allow split of neighbors
                        return False
                    if (len(pick_artist.get_xdata()) - max_index <= 2 and
                        min_index == 0):
                        # don't allow split of last and first
                        return False
                elif (self.artists[pick_artist][self.K_OUTSIDE] ==
                      self.artists[self.split_pick_artist][self.K_OUTSIDE]):
                    # Only allow inter-object split of outside to inside
                    return False
                return True
                
            def on_split_second_click(self, event):
                if event.inaxes != self.orig_axes:
                    return
                pick_artist, pick_index = self.get_control_point(event)
                if not self.ok_to_split(pick_artist, pick_index):
                    return
                if pick_artist == self.split_pick_artist:
                    #
                    # Create two new artists from the former artist.
                    #
                    xy = pick_artist.get_xydata()
                    idx0 = min(pick_index, self.split_pick_index)
                    idx1 = max(pick_index, self.split_pick_index)
                    xy0 = np.vstack((xy[:(idx0+1), :],
                                     xy[idx1:, :]))
                    xy1 = np.vstack((xy[idx0:(idx1+1), :],
                                     xy[idx0:(idx0+1), :]))
                    pick_artist.set_data((xy0[:, 0], xy0[:, 1]))
                    new_artist = Line2D(xy1[:, 0], xy1[:, 1], animated = True)
                    new_object_number = len(self.to_keep)
                    old_object_number = self.artists[pick_artist][self.K_LABEL]
                    self.artists[new_artist] = { 
                        self.K_EDITED: True,
                        self.K_LABEL: new_object_number,
                        self.K_OUTSIDE: self.artists[pick_artist][self.K_OUTSIDE]}
                    self.orig_axes.add_line(new_artist)
                    self.artists[pick_artist][self.K_EDITED] = True
                    temp = np.ones(self.to_keep.shape[0] + 1, bool)
                    temp[:-1] = self.to_keep
                    self.to_keep = temp
                    self.close_label(old_object_number, False)
                    self.close_label(new_object_number, False)
                    self.init_labels()
                    self.make_control_points(old_object_number)
                    self.make_control_points(new_object_number)
                    self.display()
                else:
                    #
                    # Join head and tail of different objects. The opposite
                    # winding means we don't have to reverse the array.
                    # We figure out which object is inside which and 
                    # combine them to form the outside artist.
                    #
                    xy0 = self.split_pick_artist.get_xydata()
                    xy1 = pick_artist.get_xydata()
                    path0 = Path(xy0)
                    path1 = Path(xy1)
                    if path0.contains_path(path1):
                        outside_artist = self.split_pick_artist
                        inside_artist = pick_artist
                        outside_index = self.split_pick_index
                        inside_index = pick_index
                    else:
                        outside_artist = pick_artist
                        inside_artist = self.split_pick_artist
                        outside_index = pick_index
                        inside_index = self.split_pick_index
                        xy0, xy1 = xy1, xy0
                    #
                    # We move the outside and inside points in order to make
                    # a gap. border_pts's first index is 0 for the outside
                    # point and 1 for the inside point. The second index
                    # is 0 for the point to be contributed first and
                    # 1 for the point to be contributed last. 
                    #
                    border_pts = np.zeros((2,2,2))
                    for i0, (idx, a) in enumerate((
                        (outside_index, xy0), (inside_index, xy1))):
                        a = a.astype(float)
                        if idx == 0:
                            idx_left = a.shape[0] - 2
                        else:
                            idx_left = idx - 1
                        if idx == a.shape[0] - 2:
                            idx_right = 0
                        else:
                            idx_right = idx+1
                        border_pts[0, i0, :] = (a[idx_left, :]+a[idx, :])/2
                        border_pts[1, 1-i0, :]  = (a[idx_right, :]+a[idx, :])/2
                        
                    xy = np.vstack((xy0[:outside_index, :], 
                                    border_pts[:, 0, :],
                                    xy1[(inside_index+1):-1, :],
                                    xy1[:inside_index, :],
                                    border_pts[:, 1, :],
                                    xy0[(outside_index+1):, :]))
                    xy[-1, : ] = xy[0, :] # if outside_index == 0
                    
                    outside_artist.set_data((xy[:, 0], xy[:, 1]))
                    del self.artists[inside_artist]
                    inside_artist.remove()
                    object_number = self.artists[outside_artist][self.K_LABEL]
                    self.update_artists()
                self.exit_split_mode(event)
                
            ################################
            #
            # Functions for keep / remove/ toggle
            #
            ################################
    
            def on_keep(self, event):
                self.to_keep[1:] = True
                self.display()
            
            def on_remove(self, event):
                self.to_keep[1:] = False
                self.display()
            
            def on_toggle(self, event):
                self.to_keep[1:] = ~ self.to_keep[1:]
                self.display()
                
            def on_reset(self, event):
                self.labels = self.orig_labels.copy()
                self.artists = {}
                self.init_labels()
                self.display()
                
            def make_control_points(self, object_number):
                '''Create an artist with control points for editing an object
                
                object_number - # of object to edit
                '''
                #
                # For outside edges, we trace clockwise, conceptually standing 
                # to the left of the outline and putting our right hand on the
                # outline. Inside edges have the opposite winding.
                # We remember the direction we are going and that gives
                # us an order for the points. For instance, if we are going
                # north:
                #
                #  2  3  4
                #  1  x  5
                #  0  7  6
                #
                # If "1" is available, our new direction is southwest:
                #
                #  5  6  7
                #  4  x  0
                #  3  2  1
                #
                #  Take direction 0 to be northeast (i-1, j-1). We look in
                #  this order:
                #
                #  3  4  5
                #  2  x  6
                #  1  0  7
                #
                # The directions are
                #
                #  0  1  2
                #  7     3
                #  6  5  4
                #
                traversal_order = np.array(
                    #   i   j   new direction
                    ((  1,  0,  5 ),
                     (  1, -1,  6 ),
                     (  0, -1,  7 ),
                     ( -1, -1,  0 ),
                     ( -1,  0,  1 ),
                     ( -1,  1,  2 ),
                     (  0,  1,  3 ),
                     (  1,  1,  4 )))
                direction, index, ijd = np.mgrid[0:8, 0:8, 0:3]
                traversal_order = \
                    traversal_order[((direction + index) % 8), ijd]
                #
                # We need to make outlines of both objects and holes.
                # Objects are 8-connected and holes are 4-connected
                #
                for polarity, structure in (
                    (True, np.ones((3,3), bool)),
                    (False, np.array([[0, 1, 0], 
                                      [1, 1, 1], 
                                      [0, 1, 0]], bool))):
                    #
                    # Pad the mask so we don't have to deal with out of bounds
                    #
                    mask = np.zeros((self.labels.shape[0] + 2,
                                     self.labels.shape[1] + 2), bool)
                    mask[1:-1, 1:-1] = self.labels == object_number
                    if not polarity:
                        mask = ~mask
                    labels, count = scipy.ndimage.label(mask, structure)
                    if not polarity:
                        #
                        # The object touching the border is not a hole.
                        # There should only be one because of the padding.
                        #
                        border_object = labels[0,0]
                    for sub_object_number in range(1, count+1):
                        if not polarity and sub_object_number == border_object:
                            continue
                        mask = labels == sub_object_number
                        i, j = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
                        i, j = i[mask], j[mask]
                        if len(i) < 2:
                            continue
                        topleft = np.argmin(i*i+j*j)
                        chain = []
                        start_i = i[topleft]
                        start_j = j[topleft]
                        #
                        # Pick a direction that points normal and to the right
                        # from the point at the top left.
                        #
                        direction = 2
                        ic = start_i
                        jc = start_j
                        while True:
                            chain.append((ic - 1, jc - 1))
                            hits = mask[ic + traversal_order[direction, :, 0],
                                        jc + traversal_order[direction, :, 1]]
                            t = traversal_order[direction, hits, :][0, :]
                            ic += t[0]
                            jc += t[1]
                            direction = t[2]
                            if ic == start_i and jc == start_j:
                                if not polarity:
                                    # Reverse the winding order
                                    chain = chain[::-1]
                                if len(chain) > 40:
                                    markevery = min(10, int((len(chain)+ 19) / 20))
                                    chain = chain[::markevery]
                                chain.append((ic - 1, jc - 1))
                                break
                        chain = np.array(chain)
                        artist = Line2D(chain[:, 1], chain[:, 0],
                                        marker='o', markerfacecolor='r',
                                        markersize=6,
                                        color=self.colormap[object_number, :],
                                        animated = True)
                        self.orig_axes.add_line(artist)
                        self.artists[artist] = { 
                            self.K_LABEL: object_number, 
                            self.K_EDITED: False,
                            self.K_OUTSIDE: polarity}
                self.update_artists()
            
            def close_label(self, label, display = True):
                '''Close the artists associated with a label
                
                label - label # of label being closed.
                
                If edited, update the labeled pixels.
                '''
                my_artists = [artist for artist, data in self.artists.items()
                              if data[self.K_LABEL] == label]
                if any([self.artists[artist][self.K_EDITED] 
                        for artist in my_artists]):
                    #
                    # Convert polygons to labels. The assumption is that
                    # a polygon within a polygon is a hole.
                    #
                    mask = np.zeros(self.orig_labels.shape, bool)
                    for artist in my_artists:
                        j, i = artist.get_data()
                        m1 = polygon_lines_to_mask(i[:-1], j[:-1],
                                                   i[1:], j[1:],
                                                   orig_labels.shape)
                        mask[m1] = ~mask[m1]
                    self.labels[self.labels == label] = 0
                    self.labels[mask] = label
                    if display:
                        self.init_labels()
                        self.display()
                    
                for artist in my_artists:
                    artist.remove()
                    del self.artists[artist]
                if display:
                    self.update_artists()
        
        with FilterObjectsDialog(self, workspace, orig_labels) as dialog_box:
            result = dialog_box.ShowModal()
        if result != wx.OK:
            raise RuntimeError("User cancelled EditObjectsManually")
        return dialog_box.labels
    
    def get_measurement_columns(self, pipeline):
        '''Return information to use when creating database columns'''
        orig_image_name = self.object_name.value
        filtered_image_name = self.filtered_objects.value
        columns = I.get_object_measurement_columns(filtered_image_name)
        columns += [(orig_image_name,
                     I.FF_CHILDREN_COUNT % filtered_image_name,
                     cpmeas.COLTYPE_INTEGER),
                    (filtered_image_name,
                     I.FF_PARENT %  orig_image_name,
                     cpmeas.COLTYPE_INTEGER)]
        return columns
    
    def get_object_dictionary(self):
        '''Return the dictionary that's used by identify.get_object_*'''
        return { self.filtered_objects.value: [ self.object_name.value ] }
    
    def get_categories(self, pipeline, object_name):
        '''Get the measurement categories produced by this module
        
        pipeline - pipeline being run
        object_name - fetch categories for this object
        '''
        categories = self.get_object_categories(pipeline, object_name,
                                                self.get_object_dictionary())
        return categories
    
    def get_measurements(self, pipeline, object_name, category):
        '''Get the measurement features produced by this module
      
        pipeline - pipeline being run
        object_name - fetch features for this object
        category - fetch features for this category
        '''
        measurements = self.get_object_measurements(
            pipeline, object_name, category, self.get_object_dictionary())
        return measurements
    
    def upgrade_settings(self, setting_values, variable_revision_number,
                         module_name, from_matlab):
        '''Upgrade the settings written by a prior version of this module
        
        setting_values - array of string values for the module's settings
        variable_revision_number - revision number of module at time of saving
        module_name - name of module that saved settings
        from_matlab - was a pipeline saved by CP 1.0
        
        returns upgraded settings, new variable revision number and matlab flag
        '''
        if from_matlab and variable_revision_number == 2:
            object_name, filtered_object_name, outlines_name, \
            renumber_or_retain = setting_values
            
            if renumber_or_retain == "Renumber":
                renumber_or_retain = R_RENUMBER
            else:
                renumber_or_retain = R_RETAIN
            
            if outlines_name == cps.DO_NOT_USE:
                wants_outlines = cps.NO
            else:
                wants_outlines = cps.YES
            
            setting_values = [object_name, filtered_object_name,
                              wants_outlines, outlines_name, renumber_or_retain]
            variable_revision_number = 1
            from_matlab = False
            module_name = self.module_name
            
        if (not from_matlab) and variable_revision_number == 1:
            # Added wants image + image
            setting_values = setting_values + [ cps.NO, "None"]
            variable_revision_number = 2
        
        return setting_values, variable_revision_number, from_matlab
