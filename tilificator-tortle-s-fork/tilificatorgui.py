#! /usr/bin/env python
#
# Copyright (C) 2012-2018 Michel Iwaniec
#
# This file is part of Tilificator.
#
# Tilificator is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Tilificator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Tilificator.  If not, see <http://www.gnu.org/licenses/>.
#

from collections import OrderedDict

import sys
import time
import array
import itertools
import operator

from PIL import Image
import cv2

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QMainWindow, QWidget, QMenuBar, QAction, QVBoxLayout, QFormLayout, QLabel, QFileDialog, QSplitter, QFrame, QScrollArea, QGroupBox, QProgressBar, QMessageBox, QListWidget, QListWidgetItem, QListView
from PySide2.QtCore import QCoreApplication, QSize

from sprite import *
from tile import *
from cut_spritesheet import *
from import_raw_tiles import *
from tilificator import *
from optimizationdialog import *
from tilesettingsdialog import *
from AboutDialog import AboutDialog

from TilificatorProject import TilificatorProject

from TileTableWidget import TileTableWidget
from SpriteImageWidget import SpriteImageWidget

from SpriteImageWidgetDelegate import SpriteImageWidgetDelegate


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)
        hpaned = QSplitter(self.centralWidget)
        self.setMinimumSize(160, 160)
        self.resize(480, 320)

        self.optimizationSettings = OptimizationSettings()
        self.displayCoverage = True
        self.zoom = 1.0

        settings = TileSettings()
        self.tileTable = TileTable(settings)

        self.tileTableWindow = TileTableWidget(self.tileTable)

        self.tileTableWindow.TileTableUpdated.connect(self.tileTableUpdated)
        self.tileTableWindow.SelectionUpdated.connect(self.syncSelectionFromTileTableWindow)

        # create a groupbox containing a scroll area with the tile table
        self.ttScrollArea = QScrollArea(self.centralWidget)
        self.ttScrollArea.setWidget(self.tileTableWindow)
        self.ttScrollArea.setWidgetResizable(True)
        groupBoxLayout = QVBoxLayout()
        groupBoxLayout.addWidget(self.ttScrollArea)
        self.tileTableGroupBox = QGroupBox()
        self.tileTableGroupBox.setLayout(groupBoxLayout)
        hpaned.addWidget(self.tileTableGroupBox)

        self.setWindowTitle('Tilificator')
        self.resize(1000, 500)

        self.createMainMenuBar()

        self.siwLayout = QVBoxLayout()
        self.siwListWidget = QListWidget()
        self.siwListWidget.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        self.siwListWidget.setLayout(self.siwLayout)
        self.siwListWidget.setResizeMode(QListWidget.Adjust)
        self.siwDelegate = SpriteImageWidgetDelegate()
        self.siwListWidget.setItemDelegate(self.siwDelegate)
        self.siwListWidget.setDragDropMode(QListWidget.InternalMove)
        self.siwListWidget.installEventFilter(self)

        # create a groupbox containing a scroll area with sprite images list widget
        self.siwScrollArea = QScrollArea(self.centralWidget)
        self.siwScrollArea.setWidget(self.siwListWidget)
        self.siwScrollArea.setWidgetResizable(True)
        groupBoxLayout = QVBoxLayout()
        groupBoxLayout.addWidget(self.siwScrollArea)
        self.siwGroupBox = QGroupBox()
        self.siwGroupBox.setLayout(groupBoxLayout)
        hpaned.addWidget(self.siwGroupBox)

        layout = QVBoxLayout()
        layout.addWidget(hpaned)
        self.centralWidget.setLayout(layout)

        self.set_zoom(4)
        self.show()

    def eventFilter(self, widget, event):
        if (widget is self.siwListWidget):
            if event.type() == QtCore.QEvent.ContextMenu:
                menu = QtWidgets.QMenu()
                menu.addAction('Tilify this sprite image')
                menu.addAction('Delete this sprite image')
                action = menu.exec_(event.globalPos())
                if action:
                    if action.text() == 'Tilify this sprite image':
                        self.tilifySelected(action)
                    if action.text() == 'Delete this sprite image':
                        self.deleteSelected(action)
            elif event.type() == QtCore.QEvent.KeyPress and event.key() == Qt.Key_Delete:
                self.deleteSelected(None)
            elif event.type() == QtCore.QEvent.KeyPress and event.key() == Qt.Key_J:
                self.decOriginX()
            elif event.type() == QtCore.QEvent.KeyPress and event.key() == Qt.Key_K:
                self.incOriginY()
            elif event.type() == QtCore.QEvent.KeyPress and event.key() == Qt.Key_L:
                self.incOriginX()
            elif event.type() == QtCore.QEvent.KeyPress and event.key() == Qt.Key_I:
                self.decOriginY()
        return super(MainWindow, self).eventFilter(widget, event)

    def incOriginX(self):
        selected = self.siwListWidget.selectedItems()
        for lwItem in selected:
            lwItem.data(Qt.DisplayRole).originX += 1
            self.siwDelegate.getEditor(lwItem.data(Qt.DisplayRole)).updateOrigin()


    def decOriginX(self):
        selected = self.siwListWidget.selectedItems()
        for lwItem in selected:
            lwItem.data(Qt.DisplayRole).originX -= 1
            self.siwDelegate.getEditor(lwItem.data(Qt.DisplayRole)).updateOrigin()

    def incOriginY(self):
        selected = self.siwListWidget.selectedItems()
        for lwItem in selected:
            lwItem.data(Qt.DisplayRole).originY += 1
            self.siwDelegate.getEditor(lwItem.data(Qt.DisplayRole)).updateOrigin()

    def decOriginY(self):
        selected = self.siwListWidget.selectedItems()
        for lwItem in selected:
            lwItem.data(Qt.DisplayRole).originY -= 1
            self.siwDelegate.getEditor(lwItem.data(Qt.DisplayRole)).updateOrigin()

    def syncSelectionFromTileTableWindow(self, widget, selection):
        for si in self.getSpriteImages():
            siw = self.siwDelegate.getEditor(si)
            blockSignalsOld = siw.blockSignals(True)
            siw.selectTiles(selection)
            siw.blockSignals(blockSignalsOld)
        self.redraw()

    def syncSelectionFromSpriteImageWindow(self, widget, selection):
        selection = []
        for si in self.getSpriteImages():
            siw = self.siwDelegate.getEditor(si)
            for tileID in siw.selection:
                if tileID not in selection:
                    selection.append(tileID)
        self.tileTableWindow.selectTiles(selection)

    def tileTableUpdated(self, widget, remapping):
        # Remap tilifications
        if remapping != []:
            for si in self.getSpriteImages():
                #si.tilification.tiles = [tile for tile in si.tilification.tiles if(tile.tileID not in selectedTiles)]
                for tile in si.tilification.tiles:
                    tile.tileID = remapping[tile.tileID]

    def getSpriteImages(self):
        spriteImages = []
        for i in range(self.siwListWidget.count()):
            lwItem = self.siwListWidget.item(i)
            spriteImages.append(lwItem.data(Qt.DisplayRole))
        return spriteImages

    def getSelectedSpriteImages(self):
        spriteImages = []
        for lwItem in self.siwListWidget.selectedItems():
            spriteImages.append(lwItem.data(Qt.DisplayRole))
        return spriteImages

    def addSpriteImage(self, si):
        if si.width > 0 and si.height > 0:
            lwItem = QListWidgetItem()
            lwItem.setData(Qt.DisplayRole, si)
            lwItem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.siwListWidget.addItem(lwItem)
            self.siwListWidget.openPersistentEditor(lwItem)
            spriteImageWindow = self.siwDelegate.getEditor(si)
            spriteImageWindow.SelectionUpdated.connect(self.syncSelectionFromSpriteImageWindow)
            self.tileTableWindow.palette = si.palette
            return None
        else:
            return None

    def getSpriteImagesGridSize(self):
        maxWidth, maxHeight = 0, 0
        for i in range(self.siwListWidget.count()):
            lwItem = self.siwListWidget.item(i)
            si = lwItem.data(Qt.DisplayRole)
            if not self.siwListWidget.isPersistentEditorOpen(lwItem):
                self.siwListWidget.openPersistentEditor(lwItem)
            siw = self.siwDelegate.getEditor(si)
            maxWidth = max(maxWidth, siw.width())
            maxHeight = max(maxHeight, siw.height())
        return maxWidth, maxHeight

    def toggleSpriteImagesGridLayout(self):
        if self.siwListWidget.viewMode() == QListWidget.ListMode:
            # Switch to IconMode
            self.siwListWidget.reset()
            self.siwListWidget.setMovement(QListWidget.Snap)
            self.siwListWidget.setViewMode(QListWidget.IconMode)
            self.redraw()
            maxWidth, maxHeight = self.getSpriteImagesGridSize()
            self.siwListWidget.setGridSize(QSize(1.25*maxWidth, 1.25*maxHeight))
        else:
            # Switch to ListMode
            self.siwListWidget.reset()
            self.siwListWidget.setMovement(QListWidget.Static)
            self.siwListWidget.setViewMode(QListWidget.ListMode)
            self.redraw()
            self.siwListWidget.setGridSize(QSize())
        self.siwListWidget.setDragDropMode(QListWidget.InternalMove)

    def deleteSelected(self, action):
        selected = self.siwListWidget.selectedItems()
        for lwItem in selected:
            self.siwListWidget.takeItem(self.siwListWidget.row(lwItem))

    def selectTileID(self, tileID):
        for i in range(self.siwListWidget.count()):
            si = self.siwListWidget.item(i).data(Qt.DisplayRole)
            siw = self.siwDelegate.getEditor(si)
            siw.selectTiles([tileID])
        self.redraw()

    def set_zoom(self, zoom):
        self.zoom = zoom
        if self.zoom < 1.0:
            self.zoom = 1.0

        self.redraw()

    def redraw(self):
        for i in range(self.siwListWidget.count()):
            lwItem = self.siwListWidget.item(i)
            si = lwItem.data(Qt.DisplayRole)
            if not self.siwListWidget.isPersistentEditorOpen(lwItem):
                self.siwListWidget.openPersistentEditor(lwItem)
            siw = self.siwDelegate.getEditor(si)
            settings = self.tileTable.settings
            siw.rectanglesWidget.padLeft = settings.tileWidth
            siw.rectanglesWidget.padRight = settings.tileWidth
            # Use asymmetric verical padding, as QListWidget translates the editor widget for unknown reasons
            siw.rectanglesWidget.padTop = int(1.0 * settings.tileHeight)
            siw.rectanglesWidget.padBottom = int(1.5 * settings.tileHeight)
            siw.rectanglesWidget.zoom = self.zoom
        self.siwListWidget.model().layoutChanged.emit()
        self.tileTableWindow.redraw()
        self.tileTableGroupBox.setTitle(' {} tiles '.format(self.tileTable.numTiles))
        self.siwGroupBox.setTitle(' {} sprite images '.format(self.siwListWidget.count()))

    def createMainMenuBar(self):
        menus = OrderedDict([('File', [('New', None, '&New project', 'Ctrl+N', None, self.newWorkspace),
                                       ('Open', None, '&Open project', 'Ctrl+O', None, self.openWorkspace),
                                       ('Save', None, '&Save project', 'Ctrl+S', None, self.saveWorkspace),
                                       ('Quit', QtGui.QIcon('exit.png'), '&Quit', 'Ctrl+Q', None, self.close)]),

                             ('TileTable', [('InvertSelection', None, '&Invert selection', None, None, self.invertSelection),
                                            ('SelectUsed', None, 'Select &used', None, None, self.selectUsed),
                                            ('ClearTiles', None, '&Clear tile table', None, None, self.clearTileTable),
                                            ('ImportRawTiles', None, '&Import RAW tile data', None, None, self.importRawTiles),
                                            ('ExportRawTiles', None, '&Export RAW tile data', None, None, self.exportRawTiles),
                                            ('TileTableSettings', None, '&Settings', None, None, self.tileTableSettings)]),
                             ('SpriteImages', [('ImportSpriteSheet', None, 'Import sprite images from sheet', None, None, self.loadSpriteSheet),
                                               ('ImportSpriteImages', None, 'Import sprite images', None, None, self.loadSpriteImages),
                                               ('TilifyAll', None, '&Tilify all', None, None, self.tilifyAll),
                                               ('ClearSpriteImages', None, 'Clear all sprite images', None, None, self.clearSpriteImages),
                                               ('TilifySpriteImage', None, 'Tilify selected', None, None, self.tilifySelected),
                                               ('DeleteSpriteImage', None, 'Delete selected', None, None, self.deleteSelected),
                                               ('ExportSpriteSheet', None, 'Export Sprite Sheet', None, None, self.exportSpriteSheet),
                                               ('GridLayout', None, 'Grid layout', None, False, self.toggleSpriteImagesGridLayout)]),
                             
                             ('Help', [('About', None, '&About', None, None, lambda a: AboutDialog().exec_())])])

        menuBar = self.menuBar()
        for menuName, menuActions in menus.items():
            menu = menuBar.addMenu(menuName)
            for action in menuActions:
                name, icon, text, shortCut, isChecked, slot = action
                qAction = QAction(QtGui.QIcon('exit.png'), text, self)
                qAction.setShortcut(shortCut)
                qAction.setStatusTip(text)
                if isChecked is not None:
                    qAction.setCheckable(True)
                    qAction.setChecked(isChecked)
                    qAction.toggled.connect(slot)
                else:
                    qAction.triggered.connect(slot)
                menu.addAction(qAction)
                #menu.addAction(icon, text, None, slot, QKeySequence(shortCut))

    def saveSpriteTilifications(self):
        filename, fileType = QFileDialog.getSaveFileName(parent=self,
                                                         caption='Save tilification data to file',
                                                         filter='Text output (*.txt)')
        if filename != '':
            self.saveSpriteTilificationsAs(filename)

    def saveSpriteTilificationsAs(self, filename):
        file = open(filename, "w")
        for i in range(self.siwListWidget.count()):
            settings = self.tileTable.settings
            si = self.siwListWidget.item(i).data(Qt.DisplayRole)
            xoffs = -(si.width / 2) - settings.tileWidth
            yoffs = -(si.height - 1) - settings.tileHeight
            file.writelines(['SpriteImage %d %d %d %d\n' % (i, len(si.tilification.tiles), xoffs, yoffs)])
            for t in si.tilification.tiles:
                s = '  ' + str(t.x + settings.tileWidth) + ',' + str(t.y + settings.tileHeight) + ',' + str(t.tileID) + ',' + str(t.flipH) + ',' + str(t.flipV) + '\n'
                file.writelines([s])

    def tilifySelected(self, action):
        self.tilify(self.getSelectedSpriteImages())

    def tilifyAll(self, action):
        self.tilify(self.getSpriteImages())

    def splitSpriteImages(self, spriteImages):
        """
        Splits a list of sprite images into color-separated ones.
        """
        spriteImagesSplit = []
        unsplitToSplitMap = []
        for i, spriteImage in enumerate(spriteImages):
            splitImages = splitLayeredImage(spriteImage, self.tileTable.settings)
            splitIndices = []
            for si in splitImages:
                splitIndices.append(len(spriteImagesSplit))
                spriteImagesSplit.append(si)
            unsplitToSplitMap.append(splitIndices)
        return spriteImagesSplit, unsplitToSplitMap

    def tilify(self, spriteImages):
        dialog = OptimizationSettingsDialog(self.optimizationSettings, parent=self)
        response = dialog.exec_()
        if response == QDialog.Accepted:
            self.clearTilifications()
            self.optimizationSettings = dialog.getOptimizationSettings()
            self.tileTableWindow.tileTableChanged()
            self.redraw()
            progressBarGMI1 = QProgressBar()
            progressBarGMI2 = QProgressBar()
            # Progress bars for tilification
            progressBar = QProgressBar()
            label = QLabel('Image 0 progress')
            progressBarTotal = QProgressBar()
            progressDialog = QDialog(self)
            progressDialog.setWindowTitle('Tilifying - please wait...')
            # Ok/Cancel buttons
            buttonBox = QDialogButtonBox(QDialogButtonBox.Cancel)
            # Form layout
            layout = QFormLayout()
            if self.optimizationSettings.useGlobalOptimization:
                layout.addRow('Global Optimization pre-processing #1', progressBarGMI1)
                layout.addRow('Global Optimization pre-processing #2', progressBarGMI2)
            layout.addRow(label, progressBar)
            layout.addRow('Total progress', progressBarTotal)
            layout.addRow(buttonBox)
            progressDialog.setLayout(layout)

            startTime = time.time()
            progressDialog.show()

            # Split multi-palette images
            splitImages, unsplitToSplitMap = self.splitSpriteImages(spriteImages)

            if self.optimizationSettings.useGlobalOptimization:
                progressBarGMI1.setRange(0, len(splitImages))
                for i, si in enumerate(splitImages):
                    generateSpriteImageLookups(self.tileTable, si)
                    progressBarGMI1.setValue(i)
                    QCoreApplication.processEvents()
                progressBarGMI1.setValue(len(splitImages))
                # Create match images for each combination of images
                progressBarGMI2.setRange(0, len(splitImages)**2)
                for globalMatchDict in generateMatchImageDict(self.tileTable, splitImages):
                    progressBarGMI2.setValue(len(globalMatchDict))
                    QCoreApplication.processEvents()
                progressBarGMI2.setValue(len(splitImages)**2)

            progressBarTotal.setRange(0, len(spriteImages))
            for spriteImageIndex, spriteImage in enumerate(spriteImages):
                siw = self.siwDelegate.getEditor(spriteImage)
                progressDialog.setWindowTitle('Tilifying sprite image {} of {}...'.format(spriteImageIndex, len(spriteImages)))
                label.setText('Image {} progress'.format(spriteImageIndex))
                progressBar.setRange(0, 100)
                for i, splitImageIndex in enumerate(unsplitToSplitMap[spriteImageIndex]):
                    si = splitImages[splitImageIndex]
                    # previousTilification needs setting, so that cost-function gets evaluated correctly
                    if i > 0:
                        si.previousTilification = splitImages[unsplitToSplitMap[spriteImageIndex][i - 1]].tilification.tiles
                    else:
                        si.previousTilification = []
                    if self.optimizationSettings.useGlobalOptimization:
                        # Create new global-match-image, using only the not-yet-tilified images
                        si.globalMatches = generateGlobalMatchImage(self.tileTable,
                                                                    splitImages,
                                                                    globalMatchDict,
                                                                    splitImageIndex,
                                                                    range(splitImageIndex + 1, len(splitImages)),
                                                                    self.optimizationSettings.solidFactorExponent)
                        # si.save('spriteimage_{}.png'.format(splitImageIndex))
                        #self.saveArray2d(si.globalMatches, 'gmimageremain_{}.png'.format(splitImageIndex), 16)

                    for progress in tilifySpriteImage(si, self.tileTable, self.optimizationSettings):
                        # Only update for first split image - assumes that additional other-palette sprites are tiny'n'cheap
                        if i == 0:
                            progressBar.setValue(int(100 * progress))
                            QCoreApplication.processEvents()
                progressBarTotal.setValue(spriteImageIndex)
                QCoreApplication.processEvents()
                # Merge tilifications from split image back into original
                spriteImage.tilification = mergeTilifications([splitImages[i] for i in unsplitToSplitMap[spriteImageIndex]])
                # Make hardware sprites editable by using duck typing to treat them like rectangles
                siw.spriteTilesUpdated()
                self.tileTableWindow.tileTableChanged()
                self.tileTableUpdated(None, [])
                self.redraw()
                siw.rectanglesWidget.imageChanged()

            endTime = time.time()
            print('Total time for tilifying: ' + str(endTime - startTime) + ' seconds.')

            progressDialog.destroy()

            self.tileTableWindow.tileTableChanged()
            self.redraw()

            # Automatic save and quit when profiling...
            # self.saveWorkspaceAs("profiled.tilification_workspace")

    def saveArray2d(self, a, filename, multiplier=1):
        """
        Saves an array2d as an indexed image clamped to 0-255, with optional multiplier.
        """
        width = a.width
        height = a.height
        image = Image.frombuffer('P', (width, height), a, 'raw', 'P', 0, 1)
        palette = array.array('B', [0] * 256 * 3)
        for i in range(256):
            shade = min(int(multiplier * i), 255)
            palette[3 * i + 0] = shade
            palette[3 * i + 1] = shade
            palette[3 * i + 2] = shade
        image.putpalette(palette)
        image.save(filename)

    def invertSelection(self, action):
        selectionInverted = [tileID for tileID in range(0, self.tileTable.numTiles)
                             if tileID not in self.tileTableWindow.selection]
        self.tileTableWindow.selectTiles(selectionInverted)

    def selectUsed(self, action):
        selection = []
        for si in self.getSpriteImages():
            for st in si.tilification.tiles:
                selection.append(st.tileID)
        selection.sort()
        self.tileTableWindow.selectTiles(selection)

    def clearTileTable(self, action):
        self.tileTable.clear()
        self.tileTableWindow.tileTableChanged()
        self.tileTableWindow.redraw()
        self.clearTilifications()

    def clearSpriteImages(self, action=None):
        while self.siwListWidget.count() > 0:
            self.siwListWidget.takeItem(0)

    def clearTilifications(self):
        for si in self.getSpriteImages():
            si.tilification = Tilification()
            siw = self.siwDelegate.getEditor(si)
            siw.spriteTilesUpdated()

    def tileTableSettings(self, action):
        old = self.tileTable.settings
        dialog = TileSettingsDialog(old)
        response = dialog.exec_()
        if response == QDialog.Accepted:
            new = dialog.getTileSettings()
            # Wipe tile table if width/height settings differ
            if new.tileWidth != old.tileWidth or new.tileHeight != old.tileHeight:
                self.tileTable.clear()
                self.tileTableWindow.tileTableChanged()
            # Reduce colors if new color size is smaller
            elif new.colorSize < old.colorSize:
                tileSize = old.tileWidth * old.tileHeight
                numTiles = self.tileTable.numTiles
                newData = self.tileTable.data[:]
                for i, c in enumerate(newData):
                    newData[i] = newData[i] % new.colorSize
                self.tileTable.clear()
                for i in range(numTiles):
                    self.tileTable.addTile(newData[tileSize * i:tileSize * (i + 1)])
                self.tileTableWindow.tileTableChanged()
            self.tileTable.settings = new

    def loadSpriteImages(self, action):
        filenames, fileType = QFileDialog.getOpenFileNames(parent=self,
                                                           caption='Load sprite images',
                                                           filter='PNG images (*.png)')
        if filenames != []:
            for filename in filenames:
                si = SpriteImage(filename)
                self.addSpriteImage(si)
                self.tileTableWindow.palette = si.palette
            self.tileTableWindow.tileTableChanged()
            self.redraw()

    def loadSpriteSheet(self, action):
        filename, fileType = QFileDialog.getOpenFileName(parent=self,
                                                         caption='Load sprite sheet',
                                                         filter='PNG image (*.png)')
        if filename != '':
            oldimage = Image.open(filename)
            print(oldimage.getpalette())
            if oldimage.mode != 'P':
                QMessageBox('Only 8-bit paletted images are supported')
                return
            pal = oldimage.getpalette()[0:24]
            image = oldimage.putpalette(pal)
            print(type(image))
            # Create the CutSpriteSheetDialog and run it
            dialog = CutSpriteSheetDialog(image)
            response = dialog.exec_()
            if response == QDialog.Accepted:
                self.clearSpriteImages()
                for image in dialog.getImages():
                    si = SpriteImage()
                    si.width, si.height = image.size
                    si.data = array.array('B', image.getdata())
                    si.palette = array.array('B', image.getpalette())
                    si.tilification = Tilification()
                    self.addSpriteImage(si)
                    self.tileTableWindow.palette = si.palette
            self.tileTableWindow.tileTableChanged()
            self.redraw()

    def importRawTiles(self, action):
        dialog = ImportRawTilesDialog()
        response = dialog.exec_()
        if response == QDialog.Accepted:
            tilesData, numTiles, w, h = dialog.get_tiles()
            for i in range(numTiles):
                settings = self.tileTable.settings
                tileDataSize = settings.tileWidth * settings.tileHeight
                tileData = array.array('B', tilesData[i * tileDataSize:(i + 1) * tileDataSize])
                self.tileTable.addTile(tileData)
            self.tileTableWindow.tileTableChanged()

    def exportRawTiles(self, action):
        dialog = ExportRawTilesDialog()
        response = dialog.exec_()
        if response == QDialog.Accepted:
            settings = self.tileTable.settings
            dialog.write_tiles(self.tileTable.data, self.tileTable.numTiles)

    def exportSpriteSheet(self, action):
        dialog = ExportSpriteSheetDialog()
        response = dialog.exec_()
        if response == QDialog.Accepted:
            settings = self.tileTable.settings
            dialog.write_spritesheet(self.getSpriteImages(), len(self.getSpriteImages()))

    def newWorkspace(self, action):
        self.clearSpriteImages()
        settings = TileSettings()
        self.tileTable = TileTable(settings)
        self.tileTableWindow.tileTable = self.tileTable

    def openWorkspace(self, action):
        filename, fileType = QFileDialog.getOpenFileName(parent=self,
                                                         caption='Open project',
                                                         filter='Tilificator project (*.tpr)')
        if filename != '':
            self.openWorkspaceAs(filename)

    def openWorkspaceAs(self, filename):
        with open(filename) as f:
            self.newWorkspace(None)
            project = TilificatorProject()
            project.read(f)
            self.optimizationSettings.tilingMethod = project.optimizationSettings.tilingMethod
            self.optimizationSettings.priorities = project.optimizationSettings.priorities[:]
            self.optimizationSettings.spritesScanlineMaxLimit = project.optimizationSettings.spritesScanlineMaxLimit
            self.optimizationSettings.spritesScanlineAvgLimit = project.optimizationSettings.spritesScanlineAvgLimit
            self.tileTable = project.tileTable
            self.tileTableWindow.tileTable = project.tileTable
            self.tileTableWindow.palette = project.palette
            self.tileTableWindow.tileTableChanged()
            for si in project.spriteImages:
                siw = self.addSpriteImage(si)
            self.show()
            self.redraw()

    def saveWorkspace(self, action):
        filename, fileType = QFileDialog.getSaveFileName(parent=self,
                                                         caption='Save project',
                                                         filter='Tilificator project (*.tpr)')
        if filename != '':
            self.saveWorkspaceAs(filename)

    def saveWorkspaceAs(self, filename):
        with open(filename, "w") as f:
            project = TilificatorProject()
            project.optimizationSettings = self.optimizationSettings
            project.tileTable = self.tileTable
            project.spriteImages = self.getSpriteImages()
            project.palette = self.tileTableWindow.palette
            project.write(f)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = MainWindow()
    if len(sys.argv) == 2:
        mainWindow.openWorkspaceAs(sys.argv[1])
    sys.exit(app.exec_())
