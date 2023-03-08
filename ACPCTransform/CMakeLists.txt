
#-----------------------------------------------------------------------------
set(MODULE_NAME ACPCTransform)

#-----------------------------------------------------------------------------

#
# SlicerExecutionModel
#
find_package(SlicerExecutionModel REQUIRED)
include(${SlicerExecutionModel_USE_FILE})

#
# ITK
#
set(${PROJECT_NAME}_ITK_COMPONENTS
  ITKIOImageBase
#  ITKSmoothing
  )
find_package(ITK 4.6 COMPONENTS ${${PROJECT_NAME}_ITK_COMPONENTS} REQUIRED)
if(ITK_VERSION VERSION_GREATER_EQUAL "5.3")
  foreach(factory_uc IN ITEMS "IMAGEIO" "MESHIO" "TRANSFORMIO")
    set(ITK_NO_${factory_uc}_FACTORY_REGISTER_MANAGER 1)
  endforeach()
else()
  set(ITK_NO_IO_FACTORY_REGISTER_MANAGER 1) # See Libs/ITKFactoryRegistration/CMakeLists.txt
endif()
include(${ITK_USE_FILE})

#-----------------------------------------------------------------------------
set(MODULE_INCLUDE_DIRECTORIES
  ${vtkTeem_INCLUDE_DIRS}
  ${MRMLCore_INCLUDE_DIRS}
  ${vtkITK_INCLUDE_DIRS}
  ${SlicerBaseCLI_SOURCE_DIR}
  ${SlicerBaseCLI_BINARY_DIR}
  ${vtkSlicerMarkupsModuleMRML_INCLUDE_DIRS}
  )

set(MODULE_SRCS
  vtkPrincipalAxesAlign.cxx
  )

set(MODULE_TARGET_LIBRARIES
  #ModuleDescriptionParser
  ${ITK_LIBRARIES}
  vtkTeem
  MRMLCore
  #SlicerBaseCLI
  ${VTK_LIBRARIES}
  vtkSlicerMarkupsModuleMRML
  )

#-----------------------------------------------------------------------------
SEMMacroBuildCLI(
  NAME ${MODULE_NAME}
  TARGET_LIBRARIES ${MODULE_TARGET_LIBRARIES}
  INCLUDE_DIRECTORIES ${MODULE_INCLUDE_DIRECTORIES}
  ADDITIONAL_SRCS ${MODULE_SRCS}
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)
  add_subdirectory(Testing)
endif()
