// region resizing
const container = document.querySelector('.container');
const myDeclDiv = document.querySelector('#myDeclDiv');
const myMainDiv = document.querySelector('#myMainDiv');
const myRefDiv = document.querySelector('#myRefDiv');
const myInhDiv = document.querySelector('#myInhDiv');
const resizer = document.querySelector('#resizer');

let isResizing = false;
let lastDownX = 0;

resizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    lastDownX = e.clientX;
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;

    const offset = e.clientX - lastDownX;
    const newLeftWidth = myDeclDiv.offsetWidth + offset;
    const newRightWidth = myMainDiv.offsetWidth - offset;

    myDeclDiv.style.width = `${newLeftWidth}px`;
    myMainDiv.style.width = `${newRightWidth}px`;
    window.myDeclGraph.requestUpdate();
    window.mainGraph.requestUpdate();

    lastDownX = e.clientX;
});

document.addEventListener('mouseup', () => {
    isResizing = false;
});
// endregion resizing

// region modal
$(document).ready(function() {

    // Add a keyboard shortcut listener
    $(document).keydown(function(e) {
        // Key code for "?" is 191
        if (e.keyCode == 191) {
            // Prevent the default action (e.g., entering "?" into a text field)
            e.preventDefault();

            // Open the modal
            $('.ui.overlay.fullscreen.modal').modal('show');
        }
    });
});
// endregion modal

// region fomantic-ui
$('button').popup();

$('#graphSelection').dropdown({
    onChange: function(value, text, $selectedItem) {
        console.debug('graphSelection onChange', value, text, $selectedItem)
        if (value === 'inhGraph') {
            myRefDiv.style.display = 'none';
            myInhDiv.style.display = 'block';
            window.mainGraph = window.inhGraph;
        }
        else if (value === 'refGraph') {
            myRefDiv.style.display = 'block';
            myInhDiv.style.display = 'none';
            window.mainGraph = window.refGraph;
        }
    }
});
// endregion fomantic-ui

// region utils
const $$ = go.GraphObject.make;

function iterator_to_array(it) {
    ret = []
    while (it.next()) {
        ret.push(it.value)
    }
    return ret
}

const { folders, files, contracts, functions, links } = window.model;
console.log(
    folders.length,
    files.length,
    contracts.length,
    functions.length,
    links.function_references.length,
)
// endregion utils
