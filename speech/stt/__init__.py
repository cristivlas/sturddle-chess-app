"""
Sturddlefish Chess App (c) 2022, 2023 Cristian Vlasceanu
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
from kivy.utils import platform

if platform == 'android':
    from .android import AndroidSTT as STT
elif platform == 'ios':
    from .base import STT
else:
    try:
        import whisper
        from .whisper import WhisperSTT as STT
    except:
        from .generic import GenericSTT as STT

stt = STT()
