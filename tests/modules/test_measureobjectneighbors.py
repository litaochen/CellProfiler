"""test_measureobjectneighbors.py Test the MeasureObjectNeighbors module
"""

import numpy as np
from six.moves import StringIO

from cellprofiler.preferences import set_headless

set_headless()

import cellprofiler.pipeline as cpp
import cellprofiler.image as cpi
import cellprofiler.measurement as cpmeas
import cellprofiler.object as cpo
import cellprofiler.workspace as cpw
import cellprofiler.modules.measureobjectneighbors as M

OBJECTS_NAME = "objectsname"
NEIGHBORS_NAME = "neighborsname"


class TestMeasureObjectNeighbors:
    def make_workspace(self, labels, mode, distance=0, neighbors_labels=None):
        """Make a workspace for testing MeasureObjectNeighbors"""
        module = M.MeasureObjectNeighbors()
        module.set_module_num(1)
        module.object_name.value = OBJECTS_NAME
        module.distance_method.value = mode
        module.distance.value = distance
        pipeline = cpp.Pipeline()
        pipeline.add_module(module)
        object_set = cpo.ObjectSet()
        image_set_list = cpi.ImageSetList()
        image_set = image_set_list.get_image_set(0)
        measurements = cpmeas.Measurements()
        measurements.group_index = 1
        measurements.group_number = 1
        workspace = cpw.Workspace(
            pipeline, module, image_set, object_set, measurements, image_set_list
        )
        objects = cpo.Objects()
        objects.segmented = labels
        object_set.add_objects(objects, OBJECTS_NAME)
        if neighbors_labels is None:
            module.neighbors_name.value = OBJECTS_NAME
        else:
            module.neighbors_name.value = NEIGHBORS_NAME
            objects = cpo.Objects()
            objects.segmented = neighbors_labels
            object_set.add_objects(objects, NEIGHBORS_NAME)
        return workspace, module

    def test_load_v2(self):
        data = r"""CellProfiler Pipeline: http://www.cellprofiler.org
Version:1
SVNRevision:11016

MeasureObjectNeighbors:[module_num:1|svn_version:\'Unknown\'|variable_revision_number:2|show_window:True|notes:\x5B\x5D]
    Select objects to measure:glia
    Select neighboring objects to measure:neurites
    Method to determine neighbors:Expand until adjacent
    Neighbor distance:2
    Retain the image of objects colored by numbers of neighbors for use later in the pipeline (for example, in SaveImages)?:No
    Name the output image:countimage
    Select colormap:pink
    Retain the image of objects colored by percent of touching pixels for use later in the pipeline (for example, in SaveImages)?:No
    Name the output image:touchingimage
    Select a colormap:purple
"""
        pipeline = cpp.Pipeline()

        def callback(caller, event):
            assert not isinstance(event, cpp.LoadExceptionEvent)

        pipeline.add_listener(callback)
        pipeline.load(StringIO(data))
        assert len(pipeline.modules()) == 1
        module = pipeline.modules()[0]
        assert isinstance(module, M.MeasureObjectNeighbors)
        assert module.object_name == "glia"
        assert module.neighbors_name == "neurites"
        assert module.distance_method == M.D_EXPAND
        assert module.distance == 2
        assert not module.wants_count_image
        assert module.count_image_name == "countimage"
        assert module.count_colormap == "pink"
        assert not module.wants_percent_touching_image
        assert module.touching_image_name == "touchingimage"
        assert module.touching_colormap == "purple"

    def test_empty(self):
        """Test a labels matrix with no objects"""
        workspace, module = self.make_workspace(np.zeros((10, 10), int), M.D_EXPAND, 5)
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Expanded"
        )
        assert len(neighbors) == 0
        features = m.get_feature_names(OBJECTS_NAME)
        columns = module.get_measurement_columns(workspace.pipeline)
        assert len(features) == len(columns)
        for column in columns:
            assert column[0] == OBJECTS_NAME
            assert column[1] in features
            assert column[2] == (
                cpmeas.COLTYPE_INTEGER
                if column[1].find("Number") != -1
                else cpmeas.COLTYPE_FLOAT
            )

    def test_one(self):
        """Test a labels matrix with a single object"""
        labels = np.zeros((10, 10), int)
        labels[3:5, 4:6] = 1
        workspace, module = self.make_workspace(labels, M.D_EXPAND, 5)
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Expanded"
        )
        assert len(neighbors) == 1
        assert neighbors[0] == 0
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Expanded"
        )
        assert len(pct) == 1
        assert pct[0] == 0

    def test_two_expand(self):
        """Test a labels matrix with two objects"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1
        labels[8, 7] = 2
        workspace, module = self.make_workspace(labels, M.D_EXPAND, 5)
        module.run(workspace)
        assert tuple(module.get_categories(None, OBJECTS_NAME)) == ("Neighbors",)
        assert tuple(module.get_measurements(None, OBJECTS_NAME, "Neighbors")) == tuple(
            M.M_ALL
        )
        assert tuple(
            module.get_measurement_scales(
                None, OBJECTS_NAME, "Neighbors", "NumberOfNeighbors", None
            )
        ) == ("Expanded",)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Expanded"
        )
        assert len(neighbors) == 2
        assert np.all(neighbors == 1)
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Expanded"
        )
        #
        # This is what the patch looks like:
        #  P P P P P P P P P P
        #  P I I I I I I I O O
        #  P I I I I I O O O N
        #  P I I I I O O N N N
        #  P I I I O O N N N N
        #  P I I O O N N N N N
        #  P I O O N N N N N N
        #  O O O N N N N N N N
        #  O N N N N N N N N N
        #  N N N N N N N N N N
        #
        # where P = perimeter, but not overlapping the second object
        #       I = interior, not perimeter
        #       O = dilated 2nd object overlaps perimeter
        #       N = neigbor object, not overlapping
        #
        # There are 33 perimeter pixels (P + O) and 17 perimeter pixels
        # that overlap the dilated neighbor (O).
        #
        assert len(pct) == 2
        assert round(abs(pct[0] - 100.0 * 17.0 / 33.0), 7) == 0
        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_Expanded"
        )
        assert len(fo) == 2
        assert fo[0] == 2
        assert fo[1] == 1
        x = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestDistance_Expanded"
        )
        assert round(abs(len(x) - 2), 7) == 0
        assert round(abs(x[0] - np.sqrt(61)), 7) == 0
        assert round(abs(x[1] - np.sqrt(61)), 7) == 0

    def test_two_not_adjacent(self):
        """Test a labels matrix with two objects, not adjacent"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1
        labels[8, 7] = 2
        workspace, module = self.make_workspace(labels, M.D_ADJACENT, 5)
        module.run(workspace)
        assert tuple(
            module.get_measurement_scales(
                None, OBJECTS_NAME, "Neighbors", "NumberOfNeighbors", None
            )
        ) == ("Adjacent",)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Adjacent"
        )
        assert len(neighbors) == 2
        assert np.all(neighbors == 0)
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Adjacent"
        )
        assert len(pct) == 2
        assert np.all(pct == 0)

    def test_adjacent(self):
        """Test a labels matrix with two objects, adjacent"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1
        labels[2, 3] = 2
        workspace, module = self.make_workspace(labels, M.D_ADJACENT, 5)
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Adjacent"
        )
        assert len(neighbors) == 2
        assert np.all(neighbors == 1)
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Adjacent"
        )
        assert len(pct) == 2
        assert round(abs(pct[0] - 100), 7) == 0
        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_Adjacent"
        )
        assert len(fo) == 2
        assert fo[0] == 2
        assert fo[1] == 1

    def test_manual_not_touching(self):
        """Test a labels matrix with two objects not touching"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1  # Pythagoras triangle 3-4-5
        labels[5, 6] = 2
        workspace, module = self.make_workspace(labels, M.D_WITHIN, 4)
        module.run(workspace)
        assert tuple(
            module.get_measurement_scales(
                None, OBJECTS_NAME, "Neighbors", "NumberOfNeighbors", None
            )
        ) == ("4",)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_4"
        )
        assert len(neighbors) == 2
        assert np.all(neighbors == 0)
        pct = m.get_current_measurement(OBJECTS_NAME, "Neighbors_PercentTouching_4")
        assert len(pct) == 2
        assert round(abs(pct[0] - 0), 7) == 0

    def test_manual_touching(self):
        """Test a labels matrix with two objects touching"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1  # Pythagoras triangle 3-4-5
        labels[5, 6] = 2
        workspace, module = self.make_workspace(labels, M.D_WITHIN, 5)
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_5"
        )
        assert len(neighbors) == 2
        assert np.all(neighbors == 1)
        pct = m.get_current_measurement(OBJECTS_NAME, "Neighbors_PercentTouching_5")
        assert len(pct) == 2
        assert round(abs(pct[0] - 100), 7) == 0

        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_5"
        )
        assert len(fo) == 2
        assert fo[0] == 2
        assert fo[1] == 1

    def test_three(self):
        """Test the angles between three objects"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1  # x=3,y=4,5 triangle
        labels[2, 5] = 2
        labels[6, 2] = 3
        workspace, module = self.make_workspace(labels, M.D_WITHIN, 5)
        module.run(workspace)
        m = workspace.measurements
        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_5"
        )
        assert len(fo) == 3
        assert fo[0] == 2
        assert fo[1] == 1
        assert fo[2] == 1
        so = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_SecondClosestObjectNumber_5"
        )
        assert len(so) == 3
        assert so[0] == 3
        assert so[1] == 3
        assert so[2] == 2
        d = m.get_current_measurement(OBJECTS_NAME, "Neighbors_SecondClosestDistance_5")
        assert len(d) == 3
        assert round(abs(d[0] - 4), 7) == 0
        assert round(abs(d[1] - 5), 7) == 0
        assert round(abs(d[2] - 5), 7) == 0

        angle = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_AngleBetweenNeighbors_5"
        )
        assert len(angle) == 3
        assert round(abs(angle[0] - 90), 7) == 0
        assert round(abs(angle[1] - np.arccos(3.0 / 5.0) * 180.0 / np.pi), 7) == 0
        assert round(abs(angle[2] - np.arccos(4.0 / 5.0) * 180.0 / np.pi), 7) == 0

    def test_touching_discarded(self):
        """Make sure that we count edge-touching discarded objects

        Regression test of IMG-1012.
        """
        labels = np.zeros((10, 10), int)
        labels[2, 3] = 1
        workspace, module = self.make_workspace(labels, M.D_ADJACENT, 5)
        object_set = workspace.object_set
        assert isinstance(object_set, cpo.ObjectSet)
        objects = object_set.get_objects(OBJECTS_NAME)
        assert isinstance(objects, cpo.Objects)

        sm_labels = labels.copy() * 3
        sm_labels[-1, -1] = 1
        sm_labels[0:2, 3] = 2
        objects.small_removed_segmented = sm_labels
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Adjacent"
        )
        assert len(neighbors) == 1
        assert np.all(neighbors == 1)
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Adjacent"
        )
        assert len(pct) == 1
        assert round(abs(pct[0] - 100), 7) == 0
        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_Adjacent"
        )
        assert len(fo) == 1
        assert fo[0] == 0

        angle = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_AngleBetweenNeighbors_Adjacent"
        )
        assert len(angle) == 1
        assert not np.isnan(angle)[0]

    def test_all_discarded(self):
        """Test the case where all objects touch the edge

        Regression test of a follow-on bug to IMG-1012
        """
        labels = np.zeros((10, 10), int)
        workspace, module = self.make_workspace(labels, M.D_ADJACENT, 5)
        object_set = workspace.object_set
        assert isinstance(object_set, cpo.ObjectSet)
        objects = object_set.get_objects(OBJECTS_NAME)
        assert isinstance(objects, cpo.Objects)

        # Needs 2 objects to trigger the bug
        sm_labels = np.zeros((10, 10), int)
        sm_labels[0:2, 3] = 1
        sm_labels[-3:-1, 5] = 2
        objects.small_removed_segmented = sm_labels
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Adjacent"
        )
        assert len(neighbors) == 0
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Adjacent"
        )
        assert len(pct) == 0
        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_Adjacent"
        )
        assert len(fo) == 0

    def test_NeighborCountImage(self):
        """Test production of a neighbor-count image"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1  # x=3,y=4,5 triangle
        labels[2, 5] = 2
        labels[6, 2] = 3
        workspace, module = self.make_workspace(labels, M.D_WITHIN, 4)
        module.wants_count_image.value = True
        module.count_image_name.value = "my_image"
        module.count_colormap.value = "jet"
        module.run(workspace)
        image = workspace.image_set.get_image("my_image").pixel_data
        assert tuple(image.shape) == (10, 10, 3)
        # Everything off of the images should be black
        assert np.all(image[labels[labels == 0], :] == 0)
        # The corners should match 1 neighbor and should get the same color
        assert np.all(image[2, 5, :] == image[6, 2, :])
        # The pixel at the right angle should have a different color
        assert not np.all(image[2, 2, :] == image[2, 5, :])

    def test_PercentTouchingImage(self):
        """Test production of a percent touching image"""
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1
        labels[2, 5] = 2
        labels[6, 2] = 3
        labels[7, 2] = 3
        workspace, module = self.make_workspace(labels, M.D_WITHIN, 4)
        module.wants_percent_touching_image.value = True
        module.touching_image_name.value = "my_image"
        module.touching_colormap.value = "jet"
        module.run(workspace)
        image = workspace.image_set.get_image("my_image").pixel_data
        assert tuple(image.shape) == (10, 10, 3)
        # Everything off of the images should be black
        assert np.all(image[labels[labels == 0], :] == 0)
        # 1 and 2 are at 100 %
        assert np.all(image[2, 2, :] == image[2, 5, :])
        # 3 is at 50% and should have a different color
        assert not np.all(image[2, 2, :] == image[6, 2, :])

    def test_get_measurement_columns(self):
        """Test the get_measurement_columns method"""
        module = M.MeasureObjectNeighbors()
        module.object_name.value = OBJECTS_NAME
        module.neighbors_name.value = OBJECTS_NAME
        module.distance.value = 5
        for distance_method, scale in (
            (M.D_EXPAND, M.S_EXPANDED),
            (M.D_ADJACENT, M.S_ADJACENT),
            (M.D_WITHIN, "5"),
        ):
            module.distance_method.value = distance_method
            columns = module.get_measurement_columns(None)
            features = [
                "%s_%s_%s" % (M.C_NEIGHBORS, feature, scale) for feature in M.M_ALL
            ]
            assert len(columns) == len(features)
            for column in columns:
                assert column[1] in features, "Unexpected column name: %s" % column[1]

    def test_get_measurement_columns_neighbors(self):
        module = M.MeasureObjectNeighbors()
        module.object_name.value = OBJECTS_NAME
        module.neighbors_name.value = NEIGHBORS_NAME
        module.distance.value = 5
        for distance_method, scale in (
            (M.D_EXPAND, M.S_EXPANDED),
            (M.D_ADJACENT, M.S_ADJACENT),
            (M.D_WITHIN, "5"),
        ):
            module.distance_method.value = distance_method
            columns = module.get_measurement_columns(None)
            features = [
                "%s_%s_%s_%s" % (M.C_NEIGHBORS, feature, NEIGHBORS_NAME, scale)
                for feature in M.M_ALL
                if feature != M.M_PERCENT_TOUCHING
            ]
            assert len(columns) == len(features)
            for column in columns:
                assert column[1] in features, "Unexpected column name: %s" % column[1]

    def test_neighbors_zeros(self):
        blank_labels = np.zeros((20, 10), int)
        one_object = np.zeros((20, 10), int)
        one_object[2:-2, 2:-2] = 1

        cases = (
            (blank_labels, blank_labels, 0, 0),
            (blank_labels, one_object, 0, 1),
            (one_object, blank_labels, 1, 0),
        )
        for olabels, nlabels, ocount, ncount in cases:
            for mode in M.D_ALL:
                workspace, module = self.make_workspace(
                    olabels, mode, neighbors_labels=nlabels
                )
                assert isinstance(module, M.MeasureObjectNeighbors)
                module.run(workspace)
                m = workspace.measurements
                assert isinstance(m, cpmeas.Measurements)
                for feature in module.all_features:
                    v = m.get_current_measurement(
                        OBJECTS_NAME, module.get_measurement_name(feature)
                    )
                    assert len(v) == ocount

    def test_one_neighbor(self):
        olabels = np.zeros((20, 10), int)
        olabels[2, 2] = 1
        nlabels = np.zeros((20, 10), int)
        nlabels[-2, -2] = 1
        for mode in M.D_ALL:
            workspace, module = self.make_workspace(
                olabels, mode, distance=20, neighbors_labels=nlabels
            )
            assert isinstance(module, M.MeasureObjectNeighbors)
            module.run(workspace)
            m = workspace.measurements
            assert isinstance(m, cpmeas.Measurements)
            v = m.get_current_measurement(
                OBJECTS_NAME,
                module.get_measurement_name(M.M_FIRST_CLOSEST_OBJECT_NUMBER),
            )
            assert len(v) == 1
            assert v[0] == 1
            v = m.get_current_measurement(
                OBJECTS_NAME,
                module.get_measurement_name(M.M_SECOND_CLOSEST_OBJECT_NUMBER),
            )
            assert len(v) == 1
            assert v[0] == 0
            v = m.get_current_measurement(
                OBJECTS_NAME, module.get_measurement_name(M.M_FIRST_CLOSEST_DISTANCE)
            )
            assert len(v) == 1
            assert round(abs(v[0] - np.sqrt(16 ** 2 + 6 ** 2)), 7) == 0
            v = m.get_current_measurement(
                OBJECTS_NAME, module.get_measurement_name(M.M_NUMBER_OF_NEIGHBORS)
            )
            assert len(v) == 1
            assert v[0] == (0 if mode == M.D_ADJACENT else 1)

    def test_two_neighbors(self):
        olabels = np.zeros((20, 10), int)
        olabels[2, 2] = 1
        nlabels = np.zeros((20, 10), int)
        nlabels[5, 2] = 2
        nlabels[2, 6] = 1
        workspace, module = self.make_workspace(
            olabels, M.D_EXPAND, distance=20, neighbors_labels=nlabels
        )
        assert isinstance(module, M.MeasureObjectNeighbors)
        module.run(workspace)
        m = workspace.measurements
        assert isinstance(m, cpmeas.Measurements)
        v = m.get_current_measurement(
            OBJECTS_NAME, module.get_measurement_name(M.M_FIRST_CLOSEST_OBJECT_NUMBER)
        )
        assert len(v) == 1
        assert v[0] == 2
        v = m.get_current_measurement(
            OBJECTS_NAME, module.get_measurement_name(M.M_SECOND_CLOSEST_OBJECT_NUMBER)
        )
        assert len(v) == 1
        assert v[0] == 1
        v = m.get_current_measurement(
            OBJECTS_NAME, module.get_measurement_name(M.M_FIRST_CLOSEST_DISTANCE)
        )
        assert len(v) == 1
        assert round(abs(v[0] - 3), 7) == 0
        v = m.get_current_measurement(
            OBJECTS_NAME, module.get_measurement_name(M.M_SECOND_CLOSEST_DISTANCE)
        )
        assert len(v) == 1
        assert round(abs(v[0] - 4), 7) == 0
        v = m.get_current_measurement(
            OBJECTS_NAME, module.get_measurement_name(M.M_ANGLE_BETWEEN_NEIGHBORS)
        )
        assert len(v) == 1
        assert round(abs(v[0] - 90), 7) == 0

    def test_relationships(self):
        labels = np.array(
            [
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 1, 1, 1, 0, 0, 0, 2, 2, 2],
                [0, 1, 1, 1, 0, 0, 0, 2, 2, 2],
                [0, 1, 1, 1, 0, 0, 0, 2, 2, 2],
                [0, 0, 0, 0, 3, 3, 3, 0, 0, 0],
                [0, 0, 0, 0, 3, 3, 3, 0, 0, 0],
                [0, 0, 0, 0, 3, 3, 3, 0, 0, 0],
                [0, 4, 4, 4, 0, 0, 0, 5, 5, 5],
                [0, 4, 4, 4, 0, 0, 0, 5, 5, 5],
                [0, 4, 4, 4, 0, 0, 0, 5, 5, 5],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ]
        )

        workspace, module = self.make_workspace(labels, M.D_WITHIN, 2)
        module.run(workspace)
        m = workspace.measurements
        assert isinstance(m, cpmeas.Measurements)
        k = m.get_relationship_groups()
        assert len(k) == 1
        k = k[0]
        assert isinstance(k, cpmeas.RelationshipKey)
        assert k.module_number == 1
        assert k.object_name1 == OBJECTS_NAME
        assert k.object_name2 == OBJECTS_NAME
        assert k.relationship == cpmeas.NEIGHBORS
        r = m.get_relationships(
            k.module_number, k.relationship, k.object_name1, k.object_name2
        )
        assert len(r) == 8
        ro1 = r[cpmeas.R_FIRST_OBJECT_NUMBER]
        ro2 = r[cpmeas.R_SECOND_OBJECT_NUMBER]
        np.testing.assert_array_equal(np.unique(ro1[ro2 == 3]), np.array([1, 2, 4, 5]))
        np.testing.assert_array_equal(np.unique(ro2[ro1 == 3]), np.array([1, 2, 4, 5]))

    def test_neighbors(self):
        labels = np.array(
            [
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 1, 1, 1, 0, 0, 0, 2, 2, 2],
                [0, 1, 1, 1, 0, 0, 0, 2, 2, 2],
                [0, 1, 1, 1, 0, 0, 0, 2, 2, 2],
                [0, 0, 0, 0, 3, 3, 3, 0, 0, 0],
                [0, 0, 0, 0, 3, 3, 3, 0, 0, 0],
                [0, 0, 0, 0, 3, 3, 3, 0, 0, 0],
                [0, 4, 4, 4, 0, 0, 0, 5, 5, 5],
                [0, 4, 4, 4, 0, 0, 0, 5, 5, 5],
                [0, 4, 4, 4, 0, 0, 0, 5, 5, 5],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ]
        )

        nlabels = np.array(
            [
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
                [0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
                [0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ]
        )

        workspace, module = self.make_workspace(labels, M.D_WITHIN, 2, nlabels)
        module.run(workspace)
        m = workspace.measurements
        assert isinstance(m, cpmeas.Measurements)
        k = m.get_relationship_groups()
        assert len(k) == 1
        k = k[0]
        assert isinstance(k, cpmeas.RelationshipKey)
        assert k.module_number == 1
        assert k.object_name1 == OBJECTS_NAME
        assert k.object_name2 == NEIGHBORS_NAME
        assert k.relationship == cpmeas.NEIGHBORS
        r = m.get_relationships(
            k.module_number, k.relationship, k.object_name1, k.object_name2
        )
        assert len(r) == 3
        ro1 = r[cpmeas.R_FIRST_OBJECT_NUMBER]
        ro2 = r[cpmeas.R_SECOND_OBJECT_NUMBER]
        assert np.all(ro2 == 1)
        np.testing.assert_array_equal(np.unique(ro1), np.array([1, 3, 4]))

    def test_missing_object(self):
        # Regression test of issue 434
        #
        # Catch case of no pixels for an object
        #
        labels = np.zeros((10, 10), int)
        labels[2, 2] = 1
        labels[2, 3] = 3
        workspace, module = self.make_workspace(labels, M.D_ADJACENT, 5)
        module.run(workspace)
        m = workspace.measurements
        neighbors = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_NumberOfNeighbors_Adjacent"
        )
        np.testing.assert_array_equal(neighbors, [1, 0, 1])
        pct = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_PercentTouching_Adjacent"
        )
        np.testing.assert_array_almost_equal(pct, [100.0, 0, 100.0])
        fo = m.get_current_measurement(
            OBJECTS_NAME, "Neighbors_FirstClosestObjectNumber_Adjacent"
        )
        np.testing.assert_array_equal(fo, [3, 0, 1])

    def test_small_removed(self):
        # Regression test of issue #1179
        #
        # neighbor_objects.small_removed_segmented + objects touching border
        # with higher object numbers
        #
        neighbors = np.zeros((11, 13), int)
        neighbors[5:7, 4:8] = 1
        neighbors_unedited = np.zeros((11, 13), int)
        neighbors_unedited[5:7, 4:8] = 1
        neighbors_unedited[0:4, 4:8] = 2

        objects = np.zeros((11, 13), int)
        objects[1:6, 5:7] = 1

        workspace, module = self.make_workspace(
            objects, M.D_WITHIN, neighbors_labels=neighbors
        )
        no = workspace.object_set.get_objects(NEIGHBORS_NAME)
        no.unedited_segmented = neighbors_unedited
        no.small_removed_segmented = neighbors
        module.run(workspace)
        m = workspace.measurements
        v = m[OBJECTS_NAME, module.get_measurement_name(M.M_NUMBER_OF_NEIGHBORS), 1]
        assert len(v) == 1
        assert v[0] == 2

    def test_object_is_missing(self):
        # regression test of #1639
        #
        # Object # 2 should match neighbor # 1, but because of
        # an error in masking distances, neighbor #1 is masked out
        #
        olabels = np.zeros((20, 10), int)
        olabels[2, 2] = 2
        nlabels = np.zeros((20, 10), int)
        nlabels[2, 3] = 1
        nlabels[5, 2] = 2
        workspace, module = self.make_workspace(
            olabels, M.D_EXPAND, distance=20, neighbors_labels=nlabels
        )
        assert isinstance(module, M.MeasureObjectNeighbors)
        module.run(workspace)
        m = workspace.measurements
        assert isinstance(m, cpmeas.Measurements)
        ftr = module.get_measurement_name(M.M_FIRST_CLOSEST_OBJECT_NUMBER)
        values = m[OBJECTS_NAME, ftr]
        assert values[1] == 1

    def test_small_removed_same(self):
        # Regression test of issue #1672
        #
        # Objects with small removed failed.
        #
        objects = np.zeros((11, 13), int)
        objects[5:7, 1:3] = 1
        objects[6:8, 5:7] = 2
        objects_unedited = objects.copy()
        objects_unedited[0:2, 0:2] = 3

        workspace, module = self.make_workspace(objects, M.D_EXPAND, distance=1)
        no = workspace.object_set.get_objects(OBJECTS_NAME)
        no.unedited_segmented = objects_unedited
        no.small_removed_segmented = objects
        module.run(workspace)
        m = workspace.measurements
        v = m[OBJECTS_NAME, module.get_measurement_name(M.M_NUMBER_OF_NEIGHBORS), 1]
        assert len(v) == 2
        assert v[0] == 1
