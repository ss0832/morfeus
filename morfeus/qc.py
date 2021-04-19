"""Interface to quantum-chemical programs."""

import typing
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from morfeus.data import ANGSTROM_TO_BOHR, BOHR_TO_ANGSTROM
from morfeus.typing import ArrayLike2D
from morfeus.utils import convert_elements, Import, requires_dependency

if typing.TYPE_CHECKING:
    import qcelemental as qcel
    import qcengine as qcng


@requires_dependency([Import(module="qcengine", alias="qcng")], globals())
def optimize_qc_engine(
    elements: Union[Iterable[int], Iterable[str]],
    coordinates: ArrayLike2D,
    charge: Optional[int] = None,
    multiplicity: Optional[int] = None,
    connectivity_matrix: Optional[ArrayLike2D] = None,
    program: str = "xtb",
    model: Optional[Dict[str, Any]] = None,
    keywords: Optional[Dict[str, Any]] = None,
    local_options: Optional[Dict[str, Any]] = None,
    procedure: str = "berny",
    return_trajectory: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """Optimize molecule with QCEngine.

    Args:
        elements: Elements as atomic symbols or numbers
        coordinates: Coordinates (Å)
        charge: Molecular charge
        multiplicity: Multiplicity
        connectivity_matrix: Connectivity matrix
        program: QCEngine program
        model: QCEngine model
        keywords: QCEngine keywords
        local_options: QCEngine local options
        procedure: QCEngine procedure
        return_trajectory: Return coordinates for all steps

    Returns:
        opt_coordinates (ndarray): Conformer coordinates (Å)
        energies (ndarray): Energies for all steps (a.u.)

    Raises:
        Exception: When QCEngine calculation fails
    """
    if (
        program.lower() == "rdkit"
        and charge is not None
        and connectivity_matrix is not None
    ):
        _check_qcng_rdkit(charge, connectivity_matrix)

    # Set defaults
    if model is None:
        model = {"method": "GFN2-xTB"}
    if keywords is None:
        keywords = {}
    if local_options is None:
        local_options = {}

    # Create molecule object
    molecule = _generate_qcel_molecule(
        elements, coordinates, charge, multiplicity, connectivity_matrix
    )

    # Create optimization input
    opt_input = {
        "keywords": {"program": program},
        "input_specification": {
            "driver": "gradient",
            "model": model,
            "keywords": keywords,
        },
        "initial_molecule": molecule,
    }

    # Perform optimization
    opt = qcng.compute_procedure(
        opt_input, procedure=procedure, local_options=local_options
    )
    if not opt.success:
        raise Exception(opt.error.error_message)

    # Take out results
    energies = np.array(opt.energies)
    if return_trajectory:
        opt_coordinates = np.array(
            [result.molecule.geometry for result in opt.trajectory]
        )
    else:
        opt_coordinates = opt.final_molecule.geometry
    opt_coordinates *= BOHR_TO_ANGSTROM

    return opt_coordinates, energies


@requires_dependency([Import(module="qcengine", alias="qcng")], globals())
def sp_qc_engine(
    elements: Union[Iterable[int], Iterable[str]],
    coordinates: Sequence[Sequence[float]],
    charge: Optional[int] = None,
    multiplicity: Optional[int] = None,
    connectivity_matrix: Optional[Sequence[Sequence[int]]] = None,
    program: str = "xtb",
    model: Optional[Dict[str, Any]] = None,
    keywords: Optional[Dict[str, Any]] = None,
    local_options: Optional[Dict[str, Any]] = None,
) -> float:
    """Single-point calculation with QCEngine.

    Args:
        elements: Elements as atomic symbols or numbers
        coordinates: Coordinates (Å)
        charge: Molecular charge
        multiplicity: Molecular multiplicity
        connectivity_matrix: Connectivity matrix
        program: QCEngine program
        model: QCEngine model
        keywords: QCEngine keywords
        local_options: QCEngine local options

    Returns:
        energy: Energy (a.u.)

    Raises:
        Exception: When QCEngine calculation fails
    """
    if (
        program.lower() == "rdkit"
        and charge is not None
        and connectivity_matrix is not None
    ):
        _check_qcng_rdkit(charge, connectivity_matrix)

    # Set defaults
    if model is None:
        model = {"method": "GFN2-xTB"}
    if keywords is None:
        keywords = {}
    if local_options is None:
        local_options = {}

    # Crate molecule object
    molecule = _generate_qcel_molecule(
        elements, coordinates, charge, multiplicity, connectivity_matrix
    )

    # Create sp input
    sp_input = qcel.models.AtomicInput(
        molecule=molecule,
        driver="energy",
        model=model,
        keywords=keywords,
    )

    # Perform sp calculation
    sp = qcng.compute(sp_input, program=program, local_options=local_options)
    if not sp.success:
        raise Exception(sp.error.error_message)

    # Take out results
    energy: float = sp.return_result

    return energy


def _check_qcng_rdkit(charge: int, connectivity_matrix: ArrayLike2D) -> None:
    """Check qncg calculation for RDKit incompatibilities."""
    if charge != 0:
        raise Exception("QCEngine using RDKit does not work with charged molecules.")
    if np.any(~np.isin(connectivity_matrix, [0, 1, 2, 3])):
        raise Exception(
            "QCEngine using RDKit cannot handle bond orders different from "
            "1, 2 or 3."
        )


@requires_dependency([Import(module="qcelemental", alias="qcel")], globals())
def _generate_qcel_molecule(
    elements: Union[Iterable[int], Iterable[str]],
    coordinates: ArrayLike2D,
    charge: Optional[int] = None,
    multiplicity: Optional[int] = None,
    connectivity_matrix: Optional[ArrayLike2D] = None,
) -> qcel.models.Molecule:
    """Generate QCElemental molecule object.

    Args:
        elements: Elements as atomic symbols or numbers
        coordinates: Coordinates (Å)
        charge: Molecular charge
        multiplicity: Molecular multiplicity
        connectivity_matrix: Connectivity matrix

    Returns:
        molecule: QCElemental molecule object.
    """
    # Generate bond order list from connectivity matrix
    bos: Optional[List[Tuple[int, int, int]]]
    if connectivity_matrix is not None:
        connectivity_matrix = np.array(connectivity_matrix)
        bos = []
        i, j = np.tril_indices_from(connectivity_matrix)
        for k, l in zip(i, j):
            if k != l:
                bo = int(connectivity_matrix[k, l])
                if bo != 0:
                    bos.append((k, l, bo))
    else:
        bos = None

    # Create molecule object
    elements = np.array(convert_elements(elements, output="symbols"))
    coordinates = np.array(coordinates) * ANGSTROM_TO_BOHR
    molecule = qcel.models.Molecule(
        symbols=elements,
        geometry=coordinates,
        molecular_charge=charge,
        connectivity=bos,
        molecular_multiplicity=multiplicity,
    )

    return molecule
