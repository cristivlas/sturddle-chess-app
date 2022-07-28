"""
Sturddlefish Chess App (c) 2021, 2022 Cristian Vlasceanu
-------------------------------------------------------------------------

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
-------------------------------------------------------------------------
"""
from kivy.core.text import DEFAULT_FONT
from kivy.metrics import *
from kivy.properties import *
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.modalview import ModalView
from kivy.uix.popup import PopupException
import webbrowser



"""
Forked from standard Popup.
"""
class ModalBox(ModalView):
    close_text = StringProperty('\uF057')
    title = StringProperty('')
    title_size = NumericProperty(sp(14))
    title_font = StringProperty(DEFAULT_FONT)
    content = ObjectProperty(None)
    title_color = ColorProperty([1, 1, 1, 1])
    separator_color = ColorProperty([47 / 255., 167 / 255., 212 / 255., 1.])
    separator_height = NumericProperty(dp(2))
    _container = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # self.background = ''
        # self.background_color = 0,0,0,0

    def add_widget(self, widget, *args, **kwargs):
        if self._container:
            if self.content:
                raise PopupException('ModalBox can have only one widget as content')
            self.content = widget
        else:
            super().add_widget(widget, *args, **kwargs)

    def on_content(self, instance, value):
        if self._container:
            self._container.clear_widgets()
            self._container.add_widget(value)

    def on__container(self, instance, value):
        if value is None or self.content is None:
            return
        self._container.clear_widgets()
        self._container.add_widget(self.content)

    def on_touch_down(self, touch):
        if self.disabled and self.collide_point(*touch.pos):
            return True
        return super().on_touch_down(touch)


"""
The content of a MessageBox.
"""
class MessageBoxLayout(GridLayout):
    _box = ObjectProperty(None)
    _buttons = ObjectProperty(None)
    _message = ObjectProperty(None)

    def __init__(self, message='', user_widget=None, auto_wrap=True, **kwargs):
        super().__init__(**kwargs)
        if user_widget:
            if message:
                user_widget.size_hint = 0.55, 1
            else:
                user_widget.size_hint = 1, 1
                self._message.size_hint = None, None
                self._message.width = 0

            self._box.add_widget(user_widget)

        self._message.text = message
        self._message.on_ref_press = lambda url: webbrowser.open(url)
        self._message.auto_wrap = auto_wrap



class MessageBox:
    def __init__(self, title, message, user_widget=None, on_close=lambda *_: None, auto_wrap=True):
        self.value = None

        def _callback(btn):
            self.value = btn.text.strip()
            self.popup.dismiss()

        layout = MessageBoxLayout(message, user_widget, auto_wrap)
        if message.endswith('?'):
            for text in [ 'Yes', 'No' ]:
                layout._buttons.add_widget(Button(text=text, font_size=sp(18), on_release=_callback))
        else:
            layout._buttons.size_hint = 1,0

        self.popup = ModalBox(
            content=layout,
            on_dismiss=on_close,
            pos_hint={'center_x':.5, 'center_y':.5},
            size_hint=(0.8, 0.325),
            title=title,
            overlay_color=[0, 0, 0, .65],
        )
        self.popup.open()
