import pywinauto
from pywinauto.application import Application
from pywinauto.keyboard import send_keys
from pywinauto import keyboard as kb
from pywinauto import timings
import time
import pyautogui
import os
import sys

# Important Note: You may need to replace the images in the images folder with
# screenshots of the OMERE software from your own computer in order to ensure that 
# the program is able to recognize them 


# change the working directory to the script’s folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# start OMERE
app = Application().start(cmd_line=r"C:\Program Files (x86)\TRAD\OMERE 5.9\Omere.exe")

time.sleep(4)

atom_disp = pyautogui.locateCenterOnScreen(
    r"images\atomic_displacement.png",
    confidence=0.9
)

if atom_disp:
    pyautogui.click(atom_disp)
    time.sleep(0.1)
else:
    print("Button1 not found on screen.")

equiv_flu = pyautogui.locateCenterOnScreen(
    r"images\equivalent_fluence.png",
    confidence=0.9
)

if equiv_flu:
    pyautogui.click(equiv_flu)
    time.sleep(0.1)
else:
    print("Button2 not found on screen.")

calc_params = pyautogui.locateCenterOnScreen(
    r"images\calculation_parameters.png",
    confidence=0.9
)

if calc_params:
    pyautogui.click(calc_params)
    time.sleep(0.5)
else:
    print("Button3 not found on screen.")



proton_flu = pyautogui.locateCenterOnScreen(
    r"images\proton_equivalent_fluence.png",
    confidence=0.9
)

if proton_flu:
    pyautogui.click(proton_flu)
    time.sleep(0.1)
else:
    print("Button7 not found on screen.")


electron_flu = pyautogui.locateCenterOnScreen(
    r"images\electron_equivalent_fluence.png",
    confidence=0.9
)

if electron_flu:
    pyautogui.click(electron_flu)
    time.sleep(0.1)
else:
    print("Button8 not found on screen.")


energy_range = pyautogui.locateCenterOnScreen(
    r"images\energy_range_niel_curves.png",
    confidence=0.9
)

if energy_range:
    pyautogui.click(energy_range)
    time.sleep(0.1)
else:
    print("Button6 not found on screen.")



your_niel = pyautogui.locateCenterOnScreen(
    r"images\your_niel_data.png",
    confidence=0.9
)

if your_niel:
    pyautogui.click(your_niel)
    time.sleep(0.1)
else:
    print("Button4 not found on screen.")


niel_electrons = pyautogui.locateCenterOnScreen(
    r"images\niel_electrons.png",
    confidence=0.9
)

if niel_electrons:
    pyautogui.click(niel_electrons)
    time.sleep(0.1)
else:
    print("Button5 not found on screen.")

new_x = niel_electrons.x + 100      # move 100 pixels to the right to click on the text box
new_y = niel_electrons.y

pyautogui.moveTo(new_x, new_y)
pyautogui.click()

with open("electron_input_files.txt") as f:
    for line in f:            # loop through all of the electron input files and write their paths into the text box
        time.sleep(0.1)       # add a bit of delay to simulate human-like behavior so that nothing gets out of sync

        pyautogui.hotkey('ctrl', 'a')  # select all
        pyautogui.press('delete')      # delete to ensure nothing is in the text box

        pyautogui.typewrite(line)

        # extract the part between "\" and "." to get the filename
        filename = line.split("\\")[-1].split("_")[0]


        ok = pyautogui.locateCenterOnScreen(
            r"images\ok.png",
            confidence=0.9
        )

        if ok:
            pyautogui.click(ok)
            time.sleep(0.1)
        else:
            print("Button9 not found on screen.")


        output_file = pyautogui.locateCenterOnScreen(
            r"images\output_file.png",
            confidence=0.9
        )

        if output_file:
            time.sleep(0.1)
        else:
            print("Button5 not found on screen.")

        new_x = output_file.x + 100        # move 100 pixels to the right to click on the text box
        new_y = output_file.y

        pyautogui.moveTo(new_x, new_y)
        pyautogui.click()

        pyautogui.hotkey('ctrl', 'a')  # select all
        pyautogui.press('delete')      # delete to ensure nothing is in the text box

        output_file_name = rf"omere_outputs\{filename}_equiFlux.fle"

        pyautogui.typewrite(output_file_name)



        calc = pyautogui.locateCenterOnScreen(
            r"images\calculation.png",
            confidence=0.9
        )

        if calc:
            pyautogui.click(calc)
            time.sleep(7)
        else:
            print("Button10 not found on screen.")


        calc_params = pyautogui.locateCenterOnScreen(
            r"images\calculation_parameters.png",
            confidence=0.9
        )

        if calc_params:                         # click the Calculation Parameters button
            pyautogui.click(calc_params)
            time.sleep(0.5)
        else:
            print("Button3 not found on screen.")

        niel_electrons = pyautogui.locateCenterOnScreen(   # find the NIEL Electrons text box and continue the loop to calculate for the next element
            r"images\niel_electrons.png",
            confidence=0.9
        )

        new_x = niel_electrons.x + 100      # move 100 pixels to the right to click on the text box
        new_y = niel_electrons.y

        pyautogui.moveTo(new_x, new_y)
        pyautogui.click()



# TO DO: 
#   - Extract the necessary information from the output files (still need to figure out what info we need)




