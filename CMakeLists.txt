cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(SlicerNeuro)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/Slicer/SlicerNeuro")
set(EXTENSION_CATEGORY "Neuroimaging")
set(EXTENSION_CONTRIBUTORS "Andras Lasso (PerkLab (Queen's University))")
set(EXTENSION_DESCRIPTION "This extension provides ACPC coordinate transformation tool and installs extensions commonly needed for neuroimaging.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/Slicer/SlicerNeuro/main/SlicerNeuro.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/Slicer/SlicerNeuro/main/Docs/module_acpctransform_1.png")
set(EXTENSION_DEPENDS "UKFTractography SwissSkullStripper SlicerFreeSurfer SlicerDcm2nii SlicerDMRI HDBrainExtraction")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(ACPCTransform)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
