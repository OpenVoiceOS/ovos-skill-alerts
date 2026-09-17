/*
 * Copyright 2018 by Aditya Mehra <aix.m@outlook.com>
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.3
import QtGraphicalEffects 1.0
import Mycroft 1.0 as Mycroft
import org.kde.kirigami 2.11 as Kirigami

ItemDelegate {
    id: alarmOverViewCard
    implicitHeight: activeAlarmsViews.height - (headerLayout.height / 2)
    implicitWidth: activeAlarmsViews.count == 1 ? activeAlarmsViews.width : activeAlarmsViews.width / 2.5

    background: Rectangle {
        color: Kirigami.Theme.backgroundColor
        border.color: Kirigami.Theme.highlightColor
        border.width: 1
        radius: 6
    }

    contentItem: Item {
        id: alarmCardOverviewLayout
        anchors.fill: parent
        anchors.margins: Mycroft.Units.gridUnit + 4

        Rectangle {
            id: alarmCardColumnOne
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: Mycroft.Units.gridUnit / 4
            height: parent.height * 0.15
            color: Kirigami.Theme.backgroundColor

            RowLayout {
                id: columnOneRowLayout
                anchors.fill: parent

                Kirigami.Icon {
                    id: repeatButtonIcon
                    visible: model.alarm_repeat ? 1 : 0
                    Layout.preferredWidth: parent.height * 0.8
                    Layout.preferredHeight: width
                    Layout.alignment: Qt.AlignLeft | Qt.AlignVCenter
                    source: "media-repeat-all"
                    color: Kirigami.Theme.textColor
                }

                Label {
                    id: alarmCardRepeatLabel
                    text: model.alarm_repeatstr
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    maximumLineCount: 1
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    minimumPixelSize: 5
                    font.pixelSize: 42
                    fontSizeMode: Text.Fit
                    font.bold: true
                    color: Kirigami.Theme.textColor
                }
            }
        }

        Kirigami.Separator {
            id: alarmCardColumnOneSeparator
            anchors.top: alarmCardColumnOne.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: 1
        }

        AlarmBoxView {
            id: alarmCardColumnTwo
            anchors.top: alarmCardColumnOneSeparator.bottom
            anchors.margins: Mycroft.Units.gridUnit / 4
            anchors.left: parent.left
            anchors.right: parent.right
            height: parent.height * 0.6
            alarmName: model.alarm_name
            alarmTime: model.alarm_time
            alarmAmPm: model.alarm_daytime
            alarmExpired: model.alarm_expired
        }

        Kirigami.Separator {
            id: alarmCardColumnTwoSeparator
            anchors.top: alarmCardColumnTwo.bottom
            anchors.topMargin: Mycroft.Units.gridUnit / 4
            anchors.left: parent.left
            anchors.right: parent.right
            height: 1
        }

        AlarmButtonView {
            id: alarmCardColumnThree
            anchors.top: alarmCardColumnTwoSeparator.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.topMargin: Mycroft.Units.gridUnit / 4
            height: parent.height * 0.27
            alarmName: model.alarm_name
            alarmIndex: model.alert_id
            alarmContext: "overview"
            alarmExpired: model.alarm_expired
        }
    }
}