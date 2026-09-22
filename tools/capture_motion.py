"""Record only this application's widgets using isolated data and inert save backend."""
import os
os.environ.pop('QT_QPA_PLATFORM', None)
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QMimeData
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from creative_toolbox.ui import MainWindow, STYLE
from creative_toolbox.storage import Store, Settings
from tools.capture_assets import DemoBackend


def main():
    out=Path('artifacts/motion-frames');out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setFont(QFont('Microsoft YaHei UI' if os.name=='nt' else 'PingFang SC',10));app.setStyleSheet(STYLE)
    clipboard=app.clipboard();original=QMimeData()
    current=clipboard.mimeData()
    if current:
        for mime in current.formats(): original.setData(mime,current.data(mime))
    copied=None
    with tempfile.TemporaryDirectory() as tmp:
        window=MainWindow(DemoBackend(),Store(Path(tmp),DemoBackend.platform),Settings(),False)
        window.resize(1020,720);window.show()
        elapsed=QElapsedTimer();elapsed.start();frames=[]
        def capture():
            name=f'{len(frames):04}.png'
            shot=window.grab().scaledToWidth(1000,Qt.TransformationMode.SmoothTransformation)
            shot.save(str(out/name));frames.append({'file':name,'ms':elapsed.elapsed()})
        timer=QTimer();timer.setTimerType(Qt.TimerType.PreciseTimer);timer.timeout.connect(capture);timer.start(40)
        QTimer.singleShot(800,lambda:window.nav['library'].click())
        QTimer.singleShot(1700,lambda:window.nav['tools'].click())
        QTimer.singleShot(2600,lambda:window.open_tool('calculators'))
        def copy_result():
            nonlocal copied
            page=window.tool_pages['calculators'];copied=page.print_result.text();page.copy_result(copied)
        QTimer.singleShot(3500,copy_result)
        QTimer.singleShot(4200,lambda:window.grab().save('artifacts/copy-feedback.png'))
        QTimer.singleShot(4900,lambda:window.navigate('settings'))
        QTimer.singleShot(5800,lambda:window.reduce_motion.setChecked(True))
        QTimer.singleShot(6200,lambda:window.navigate('home'))
        def finish():
            timer.stop();capture()
            (out/'frames.json').write_text(json.dumps(frames),encoding='utf-8')
            if copied is not None and clipboard.text()==copied:
                clipboard.setMimeData(original)
            window.quit_app()
            print('Recorded',len(frames),'frames; final time',frames[-1]['ms'],'ms')
        QTimer.singleShot(7100,finish)
        app.exec()


if __name__=='__main__': main()