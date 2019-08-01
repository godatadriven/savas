import os
import sys
import logging
import subprocess

import nbformat
import nbconvert

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s - %(message)s'
)


def _cwd(nbpath):
    """
    Changes the current working directory, relative to jupyter notebook path.
    We want to emulate the %load as if we're in the notebook itself. Hence this func.
    We also return the folder and filename of the path.
    :param nbpath: Path to the notebook that needs to be tested.
    """
    logger.info(f"directory of script calling {os.getcwd()}")
    folder = os.path.dirname(nbpath)
    filename = os.path.basename(nbpath)
    if folder == "":
        folder = os.getcwd()
    os.chdir(folder)
    logger.info(f"directory for rest of script {os.getcwd()}")
    return folder, filename


def _cells(nb):
    """
    Returns a generator with reference to cells in the passed notebook.
    :param nb: Jupyter Notebook Object
    :return: generator with cell references
    """
    if nb.nbformat < 4:
        for ws in nb.worksheets:
            for cell in ws.cells:
                yield cell
    else:
        for cell in nb.cells:
            yield cell


def _strip_output(nb):
    """
    Give it a notebook and it will change all output cells to become empty.
    :param nb: Jupyter Notebook Object
    :return: Jupyter Notebook Object
    """
    nb.metadata.pop('signature', None)
    for cell in _cells(nb):
        if 'outputs' in cell:
            cell['outputs'] = []
        if 'prompt_number' in cell:
            cell['prompt_number'] = None
    return nb


def _testfile(nbpath):
    """
    Creates a path where to place a testing notebook.
    New file with have `-test.ipynb` at the end and is placed in same dir.
    :param nbpath: Path to the notebook that needs to be tested.
    """
    return nbpath.replace(".ipynb", "-test.ipynb")


def clean_notebook(nbpath):
    """
    Takes a notebook file on disk and removes all cell output.
    :param nbpath: Path to the notebook that needs to be cleaned of output.
    """
    found_paths = nbpath if isinstance(nbpath, list) else [nbpath]
    for path in found_paths:
        logger.info(f"found file {path}")
    for path in found_paths:
        logger.info(f"about to strip {path} of output")
        with open(path, 'r') as f:
            notebook = nbformat.read(f, as_version=nbformat.NO_CONVERT)
        notebook = _strip_output(notebook)
        with open(path, 'w', encoding='utf8') as f:
            nbformat.write(notebook, f)
        logger.info(f"{path} is now stripped")


def make_testable_notebook(nbpath, remove_meta=True):
    """
    Creates a new notebook that is ready for testing. New file with have `-test.ipynb` at the end.
    :param nbpath: Path to the notebook that needs to be tested.
    """
    logger.info(f"about to prepare {nbpath} for testing")
    with open(nbpath, 'r') as f:
        notebook = nbformat.read(f, as_version=nbformat.NO_CONVERT)
    if remove_meta:
        logger.info("removing kernelspec metadata from notebook as well")
        notebook['metadata']['kernelspec'] = {
            "display_name": "python",
            "language": "python",
            "name": "python"
        }
    for cell in _cells(notebook):
        if cell['cell_type'] == 'code':
            if '%load ' in cell['source']:
                logger.info(f'found %load-magic in cell with id={cell["execution_count"]}')
                logger.info(cell['source'])
                py_path = cell['source'].replace('%load ', '')
                with open(py_path, 'r') as f:
                    cell['source'] = f.read()
    nbformat.write(notebook, open(_testfile(nbpath=nbpath), mode='w'))
    logger.info(f"wrote notebook ready for testing over at {_testfile(nbpath=nbpath)}")


def test_notebook(nbpath):
    """
    Takes a path to a notebook and then:
    - prepares it for testing by making a new notebook that is testable [because %load]
    - test said temporary file with `pytest --nbval-lax`
    - remove said temporary test file
    :param nbpath: Path to the notebook that needs to be tested.
    """
    nbpath = nbpath if isinstance(nbpath, list) else [nbpath]
    current_dir = os.getcwd()
    for path in nbpath:
        os.chdir(current_dir)
        logger.info(f"about to test {path}")
        folder, filename = _cwd(path)
        make_testable_notebook(nbpath=filename)
        clean_notebook(nbpath=_testfile(filename))
        status = subprocess.call(['pytest', '--nbval-lax', '--disable-warnings', '--verbose', _testfile(nbpath=filename)])
        logger.info(f"removing temporary testing notebook {_testfile(nbpath=filename)}")
        os.remove(_testfile(nbpath=filename))
        logger.info(f"testing done for {path}")
        if status == 1:
            logger.info(f"error was found so exiting with error code 1")
            sys.exit(2)
        logger.info(f"no errors were found")


def check_files(nbpaths, verbose):
    tmpfile = "temporaryfile.py"
    for path in nbpaths:
        if os.path.splitext(path)[1] == '.ipynb':
            with open(path, 'r') as readfile:
                logger.info(f"reading {path}")
                notebook = nbformat.read(readfile, as_version=nbformat.NO_CONVERT)
            output, metadata = nbconvert.export(nbconvert.PythonExporter, notebook)
        elif os.path.splitext(path)[1] == '.py':
            with open(path, 'r') as readfile:
                output = readfile.read()
        else:
            raise ValueError("supplied file must be either .py/.ipynb")
        logger.info(f"writing {path} into {tmpfile}")
        with open(tmpfile, "a") as readfile:
            readfile.write(str(output))
        logger.info(f"added {path} to temporary file")
    if verbose:
        with open(tmpfile, "r") as f:
            for line in f.readlines():
                print(line.replace("\n", ""))
    pyfile_check_error(tmpfile)


def pyfile_check_error(tmpfile):
    try:
        exec(open(tmpfile).read())
    except AssertionError as e:
        print(e)
        logger.info(f"AssertionError detected!")
        os.remove(tmpfile)
        sys.exit(2)
    except:
        logger.info(f"something broke but it wasn't an assertion error")
        os.remove(tmpfile)
        sys.exit(2)
    os.remove(tmpfile)
    logger.info(f"{tmpfile} has been removed")
