# SlicerNeuro

Extension for 3D Slicer than installs tools commonly needed for neuroimaging, besides providing two extra modules.

# Modules

- [ACPC Transform](Docs/ACPCTransform/acpctransform.md): Calculate a transformation that aligns brain images to [Talairach coordinate system](https://en.wikipedia.org/wiki/Talairach_coordinates) (also known as stereotaxic or ACPC coordinate system) based on anatomical landmarks.
- [ImportGifti](Docs/ImportGifti/importgifti.md): Loads gifti files from a [BIDS](https://bids.neuroimaging.io/) directory to 3D Slicer and saves them as vtk files in a specified output folder. These files can be reloaded to 3D Slicer.

# Extensions

The extension automatically installs these commonly used extensions: SlicerFreeSurfer, SlicerDcm2nii, SlicerDMRI, SlicerWMA, UKFTractography, HDBrainExtraction, SwissSkullStripper.

Other neuroimaging related extensions that users need to install manually: T1Mapping, T2mapping, T1_ECVMapping, DTIPrep, DTIProcess, DTI-Reg, DTIAtlasBuilder, DTIAtlasFiberAnalyzer, DiffusionQC, SlicerNeuroSegmentation, Stereotaxia, SkullStripper, BrainVolumeRefinement, SlicerNetstim.
