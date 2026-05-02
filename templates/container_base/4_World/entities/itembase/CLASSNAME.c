class CLASSNAME : DeployableContainer_Base
{
	private bool m_IsLocked = false;
	private ref Timer m_BarrelOpener;

	protected ref OpenableBehaviour m_Openable;

	void CLASSNAME()
	{
		m_BarrelOpener = new Timer();
		m_Openable = new OpenableBehaviour(false);
		m_HalfExtents = Vector(0.30, 0.85, 0.30);

		RegisterNetSyncVariableBool("m_Openable.m_IsOpened");
		RegisterNetSyncVariableBool("m_IsSoundSynchRemote");
		RegisterNetSyncVariableBool("m_IsPlaceSound");
	}

	override int GetDamageSystemVersionChange()
	{
		return 110;
	}

	override void OnStoreSave( ParamsWriteContext ctx )
	{
		super.OnStoreSave( ctx );
		ctx.Write( m_Openable.IsOpened() );
	}

	override bool OnStoreLoad( ParamsReadContext ctx, int version )
	{
		if ( !super.OnStoreLoad( ctx, version ) )
			return false;

		bool opened;
		if ( version >= 110 && !ctx.Read( opened ) )
			return false;

		if ( opened )
			OpenLoad();
		else
			CloseLoad();

		return true;
	}

	bool IsLocked()
	{
		return m_IsLocked;
	}

	override void Open()
	{
		m_Openable.Open();
		SetTakeable(false);
		UpdateVisualState();
	}

	void OpenLoad()
	{
		m_Openable.Open();
		SetTakeable(false);
		UpdateVisualState();
	}

	override void Close()
	{
		m_Openable.Close();
		SoundSynchRemote();
		SetTakeable(true);
		UpdateVisualState();
	}

	void CloseLoad()
	{
		m_Openable.Close();
		SetTakeable(true);
		UpdateVisualState();
	}

	override bool IsOpen()
	{
		return m_Openable.IsOpened();
	}

	override void OnWasAttached( EntityAI parent, int slot_id )
	{
		super.OnWasAttached(parent, slot_id);
		Open();
	}

	override void OnWasDetached( EntityAI parent, int slot_id )
	{
		super.OnWasDetached(parent, slot_id);
		Close();
	}

	protected void UpdateVisualState()
	{
		float phase;
		if ( IsOpen() )
			phase = 1;
		else
			phase = 0;
		ANIMPHASES
	}

	override void OnVariablesSynchronized()
	{
		super.OnVariablesSynchronized();

		if ( IsPlaceSound() )
		{
			PlayPlaceSound();
		}
		else if ( IsSoundSynchRemote() && !IsBeingPlaced() && m_Initialized )
		{
			if ( IsOpen() )
				SoundBarrelOpenPlay();
			else
				SoundBarrelClosePlay();
		}

		UpdateVisualState();
	}

	void SoundBarrelOpenPlay()
	{
		EffectSound sound = SEffectManager.PlaySound("barrel_open_SoundSet", GetPosition());
		sound.SetAutodestroy(true);
	}

	void SoundBarrelClosePlay()
	{
		EffectSound sound = SEffectManager.PlaySound("barrel_close_SoundSet", GetPosition());
		sound.SetAutodestroy(true);
	}

	void Lock(float actiontime)
	{
		m_IsLocked = true;
		m_BarrelOpener.Run(actiontime, this, "Unlock", NULL, false);
	}

	void Unlock()
	{
		m_IsLocked = false;
		Open();
	}

	override bool IsContainer()
	{
		return true;
	}

	override bool IsDeployable()
	{
		return true;
	}

	override bool CanPutInCargo(EntityAI parent)
	{
		return false;
	}

	override bool CanPutIntoHands(EntityAI parent)
	{
		return false;
	}

	override bool CanReceiveItemIntoCargo( EntityAI item )
	{
		if ( IsOpen() )
			return super.CanReceiveItemIntoCargo(item);
		return false;
	}

	override bool CanReleaseCargo( EntityAI attachment )
	{
		return IsOpen();
	}

	override bool CanDetachAttachment( EntityAI parent )
	{
		if ( GetNumberOfItems() == 0 )
			return true;
		return false;
	}

	override void SetActions()
	{
		super.SetActions();
		AddAction(ActionTogglePlaceObject);
		AddAction(ActionPlaceObject);
		AddAction(ActionOpen_CLASSNAME);
		AddAction(ActionClose_CLASSNAME);
	}
};
