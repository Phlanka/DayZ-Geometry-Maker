class CfgPatches
{
	class CLASSNAME
	{
		units[]={ "CLASSNAME" };
		weapons[]={};
		requiredVersion=0.1;
		requiredAddons[]={ "DZ_Data", "DZ_Scripts", "DZ_Gear_Containers" };
	};
};

CFGMODS
class CfgVehicles
{
	class Container_Base;
	class CLASSNAME: Container_Base
	{
		scope=2;
		displayName="CHANGE ME";
		descriptionShort="CHANGE ME";
		model="MODELPATH";
		overrideDrawArea="8.0";
		forceFarBubble="true";
		slopeTolerance=0.2;
		yawPitchRollLimit[]={45,45,45};
		destroyOnEmpty=0;
		varQuantityDestroyOnMin=0;
		carveNavmesh=1;
		canBeDigged=0;
		heavyItem=1;
		weight=30000;
		itemSize[]={10,15};
		itemBehaviour=0;
		physLayer="item_large";
		allowOwnedCargoManipulation=1;
		class DamageSystem
		{
			class GlobalHealth
			{
				class Health
				{
					hitpoints=1300;
				};
			};
			class GlobalArmor
			{
				class FragGrenade
				{
					class Health
					{
						damage=8;
					};
					class Blood
					{
						damage=8;
					};
					class Shock
					{
						damage=8;
					};
				};
			};
			DAMAGEZONES
		};
		class Cargo
		{
			itemsCargoSize[]={10,30};
			openable=1;
			allowOwnedCargoManipulation=1;
		};
		ANIMSOURCES
		DOORS
		soundImpactType="metal";
		class AnimEvents
		{
			class SoundWeapon
			{
				class movement
				{
					soundSet="barrel_movement_SoundSet";
					id=1;
				};
				class pickUpItem_Light
				{
					soundSet="pickUpBarrelLight_SoundSet";
					id=796;
				};
				class pickUpItem
				{
					soundSet="pickUpBarrel_SoundSet";
					id=797;
				};
				class drop
				{
					soundset="barrel_drop_SoundSet";
					id=898;
				};
			};
		};
	};
};
